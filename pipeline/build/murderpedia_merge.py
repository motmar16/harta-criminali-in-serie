"""Faza 2: unește profilurile Murderpedia cu persoanele deja exportate (Wikidata/Wikipedia).

Se folosesc numai câmpurile structurate. „Victim profile” nu se exportă (poate conține nume de victime care nu
sunt în Wikipedia); din el se derivă doar etichete de tip (femei, copii, pacienți…).
Precedență (docs/METODOLOGIE.md): victime = Wikidata > infobox > Murderpedia; clasificare și metodă = Murderpedia
(+ etichete din Wikipedia); zonă de activitate = Wikipedia dacă e la nivel ≤ admin1, altfel Murderpedia „Location”.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from typing import Any

from pipeline.geocode import wikidata_places as wp
from pipeline.normalize import categories, dedupe, names
from pipeline.normalize.places import jitter, parse_victims
from pipeline.sources import murderpedia

log = logging.getLogger(__name__)

COUNTRY_ALIASES = {
    "usa": "US", "u.s.a.": "US", "united states": "US", "us": "US", "england": "GB", "scotland": "GB",
    "wales": "GB", "northern ireland": "GB", "uk": "GB", "united kingdom": "GB", "great britain": "GB",
    "russia": "RU", "russian federation": "RU", "ussr": "SU", "soviet union": "SU", "south korea": "KR",
    "north korea": "KP", "czech republic": "CZ", "the netherlands": "NL", "holland": "NL", "iran": "IR",
    "vietnam": "VN", "taiwan": "TW", "bolivia": "BO", "venezuela": "VE", "tanzania": "TZ", "syria": "SY",
    "ivory coast": "CI", "congo": "CD", "democratic republic of the congo": "CD", "east germany": "DE",
    "west germany": "DE", "yugoslavia": "RS", "the bahamas": "BS", "bahamas": "BS", "the philippines": "PH",
}
PRECISION_FINE = ("address", "city", "county", "admin1")
# surse euristice peste care „Location” din Murderpedia (câmp explicit despre locul crimelor) are prioritate
WEAK_AREA = {"wikipedia-lead", "wikipedia-crime-sections", "wikipedia-body", "wikipedia-list",
             "wikidata-citizenship", "none", None}


def needs_mp_area(k: dict[str, Any], first_area_place: str | None = None, mp_iso: str | None = None,
                  area_names: list[str] | None = None, mp_location: str | None = None) -> bool:
    """Murderpedia „Location” înlocuiește zona când aceasta e vagă, vine dintr-o sursă euristică slabă,
    sau coincide cu locul nașterii fără să vină din infobox (semn că am prins biografia, nu crimele)."""
    if k["coverage"]["active_area_precision"] not in PRECISION_FINE or k["sources"].get("active_area") in WEAK_AREA:
        return True
    # zonă euristică (propoziții) într-o altă țară decât cea din Murderpedia: câștigă Murderpedia
    if mp_iso and k["sources"].get("active_area") == "wikipedia-crime-sentences" and k["countries"]             and mp_iso not in k["countries"]:
        return True
    # rafinare: zona e la nivel de stat, iar Murderpedia numește orașe din același stat
    # (doar când zona are cel mult 2 state, ca să nu pierdem o arie întinsă din cauza unui singur oraș)
    if (k["coverage"]["active_area_precision"] == "admin1" and mp_location and area_names
            and len(area_names) <= 2 and mp_location.count(",") >= 2
            and any(n and n.lower() in mp_location.lower() for n in area_names)):
        return True
    birth = (k.get("birth") or {}).get("place_id")
    return bool(birth and first_area_place == birth and k["sources"].get("active_area") != "wikipedia-infobox")


def replace_area(out: dict[str, Any], k: dict[str, Any], pls: list[dict[str, Any]], source_url: str, basis: str,
                 conf: float, place_record) -> None:
    """Înlocuiește punctele `active_area` ale unei persoane (folosit de Murderpedia și de corecturile manuale)."""
    kid = k["id"]
    out["features"][:] = [f for f in out["features"]
                          if not (f["properties"]["killer_id"] == kid and f["properties"]["kind"] == "active_area")]
    feats = []
    for i, pl in enumerate(pls, 1):
        r = place_record(pl)
        out["places"][r["id"]] = r
        eid = f"{kid}-a{i:02d}"
        lat, lon = jitter(r["lat"], r["lon"], eid, r["precision"])
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {
            "id": eid, "killer_id": kid, "kind": "active_area", "date": None, "place_id": r["id"],
            "place_name": r["name"], "precision": r["precision"], "victim_count": None, "victim_label": None,
            "confidence": conf if r["precision"] != "country" else 0.4, "source_url": source_url,
            "source_quote": None, "extraction": basis}})
    out["features"].extend(feats)
    k["countries"] = list(dict.fromkeys([p["iso2"] for p in pls if p.get("iso2")] or k["countries"]))
    k["sources"]["active_area"] = basis
    k["coverage"]["active_area_points"] = len(feats)
    k["coverage"]["active_area_precision"] = feats[0]["properties"]["precision"] if feats else None


def _country_map(countries: list[dict[str, Any]]) -> dict[str, str]:
    m = {c["label"].lower(): c["iso2"] for c in countries if c.get("label")}
    m.update(COUNTRY_ALIASES)
    return m


def split_location(loc: str | None, cmap: dict[str, str]) -> tuple[str | None, str | None, list[list[str]]]:
    """„Yonkers, Westchester County, New York, USA” -> (ISO, nume țară, [[Yonkers, Westchester County, New York]]).
    „Michigan/Virginia/Ohio, USA” -> mai multe segmente."""
    if not loc:
        return None, None, []
    loc = re.sub(r"\(.*?\)", " ", loc)
    parts = [p.strip(" .") for p in loc.split(",") if p.strip(" .")]
    iso = cname = None
    if parts:
        last = parts[-1].strip().lower()
        if last in cmap:
            iso, cname = cmap[last], parts[-1].strip()
            parts = parts[:-1]
        elif "/" in last and all(x.strip().lower() in cmap for x in last.split("/")):
            parts = parts[:-1]  # mai multe țări: rămâne doar nivel de țară, ambiguu
    if not parts:
        return iso, cname, []
    # „/” separă locuri alternative: „Montreal, Quebec/Calgary, Alberta”, „Los Angeles/San Diego, California”
    segs = [[p.strip() for p in chunk.split(",") if p.strip()] for chunk in ", ".join(parts).split("/")]
    segs = [sg for sg in segs if sg]
    longest = max(segs, key=len) if segs else []
    if len(longest) > 1:
        segs = [sg + [longest[-1]] if len(sg) == 1 and sg[0] != longest[-1] else sg for sg in segs]
    return iso, cname, [[p for p in s if p] for s in segs if s]


def title_candidates(seg: list[str], cname: str | None) -> list[str]:
    """Titluri Wikipedia de încercat, de la specific la general („Yonkers, New York”, „Yonkers”, …)."""
    out = []
    if len(seg) == 1 and (cname or "").lower() in ("usa", "u.s.a.", "united states"):
        # „New York”, „Washington”, „Georgia” singure, în SUA, înseamnă statul
        out += [f"{seg[0]} (state)", f"{seg[0]} (U.S. state)"]
    last = seg[-1] if len(seg) > 1 else None
    for i, p in enumerate(seg):
        if last and p != last:
            out.append(f"{p}, {last}")
        if cname and cname.lower() not in ("usa", "uk"):
            out.append(f"{p}, {cname}")
        out.append(p)
    return list(dict.fromkeys(t for t in out if 2 < len(t) < 120))


def _ages(profile: str | None) -> list[int]:
    return [int(a) for a in re.findall(r"(?<![\d/])(\d{1,2})(?:\s*(?:years?|yrs?)(?: old)?)?(?=\s*[/),;]|$)", profile or "")]


def victim_types_mp(rec: dict[str, Any]) -> list[str]:
    vt = categories.victim_types(rec.get("victim_profile"), rec.get("characteristics"))
    ages = _ages(rec.get("victim_profile"))
    if ages and all(a < 16 for a in ages) and "children" not in vt:
        vt.append("children")
    if ages and all(a >= 65 for a in ages) and "elderly" not in vt:
        vt.append("elderly")
    return vt


def legal_from_mp(rec: dict[str, Any]) -> str | None:
    s = (rec.get("status") or "").lower()
    cls = (rec.get("classification") or "")
    if "?" in cls:
        return "suspected"
    if re.search(r"never (?:caught|identified|found)|unidentified|unsolved", s):
        return "unidentified"
    if re.search(r"acquit|not guilty|found insane|insanity", s):
        return "acquitted"
    if re.search(r"sentenced|executed|convicted|life imprisonment|years in prison|pleaded guilty|hanged on|guillotined", s):
        return "convicted"
    if re.search(r"killed by police|shot (?:to death|dead) by police|suicide|died before|committed suicide|killed himself|killed herself", s):
        return "deceased_before_trial"
    return None


def _date_iso(text: str | None) -> dict[str, Any] | None:
    from datetime import datetime
    if not text:
        return None
    t = re.sub(r"\s+", " ", text).strip()
    for fmt, prec in (("%B %d, %Y", "day"), ("%b %d, %Y", "day"), ("%B %Y", "month"), ("%Y", "year")):
        try:
            d = datetime.strptime(t, fmt)
            return {"date": d.strftime({"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}[prec]), "precision": prec}
        except ValueError:
            continue
    y = dedupe.year(t)
    return {"date": str(y), "precision": "year"} if y else None


def merge(ctx: dict[str, Any], out: dict[str, Any], place_record, area_conf: float = 0.7) -> dict[str, Any] | None:
    try:
        profiles = murderpedia.load_profiles()
    except FileNotFoundError:
        log.info("Murderpedia: nu există încă profiles.json; sar faza 2")
        return None
    cmap = _country_map(ctx["countries"])
    killers = out["killers"]
    by_id = {k["id"]: k for k in killers}
    extra = {}
    for q, p in ctx["people"].items():
        extra[q] = [v for k, vals in p["claims"].items() if k.startswith("label:") for v in vals]
        art = ctx["articles"].get(q)
        if art:
            extra[q].append(art["title"])
    matcher = dedupe.Matcher(killers, extra)
    manual = dedupe.load_manual_decisions()

    matched: dict[str, dict[str, Any]] = {}
    new: list[dict[str, Any]] = []
    ambiguous_rows = []
    stats = Counter()
    for rec in profiles:
        mtype = murderpedia.mp_type(rec)
        serial = mtype is not None  # eligibil ca persoană nouă: serial sau spree killer
        rec["_type"] = mtype
        stats["profiles"] += 1
        stats["serial"] += mtype == "serial_killer"
        stats["spree"] += mtype == "spree_killer"
        iso, cname, segs = split_location(rec.get("location"), cmap)
        rec["_iso"], rec["_cname"], rec["_segs"] = iso, cname, segs
        decision = manual.get(rec["url"])
        if decision:
            stats["manual"] += 1
            if decision in by_id:
                matched.setdefault(decision, rec)
            elif decision.lower() == "nou" and serial:
                new.append(rec)
            continue
        cands = matcher.candidates(rec, iso)
        kind, qid = dedupe.decide(cands)
        if not serial:
            # profilurile non-serial servesc doar la îmbogățire, cu potrivire strictă (an naștere confirmat)
            if kind == "match" and any(c[1] == qid and c[2] for c in cands):
                matched.setdefault(qid, rec)
                stats["matched_nonserial"] += 1
            continue
        if kind == "match":
            if qid in matched:  # două profiluri pe aceeași persoană: al doilea merge la verificare
                kind = "ambiguous"
            else:
                matched[qid] = rec
                stats["matched_serial"] += 1
                continue
        if kind == "ambiguous":
            stats["ambiguous"] += 1
            ambiguous_rows.append({
                "murderpedia_url": rec["url"], "murderpedia_nume": (rec.get("title") or "").split("|")[0].strip(),
                "nascut": rec.get("date_of_birth"), "locatie": rec.get("location"),
                "candidati": "; ".join(f"{q} {by_id[q]['names']['primary']} ({s})" for s, q, _ in cands[:4]),
            })
            continue
        new.append(rec)
    dedupe.write_ambiguous(ambiguous_rows, manual)

    # geocodare „Location” pentru: noi + potriviți fără zonă fină
    first_place, area_names = {}, {}
    for f in out["features"]:
        pr = f["properties"]
        if pr["kind"] == "active_area":
            area_names.setdefault(pr["killer_id"], []).append(pr["place_name"])
            if pr["id"].endswith("-a01"):
                first_place[pr["killer_id"]] = pr["place_id"]
    need = [r for r in new] + [r for q, r in matched.items()
                               if needs_mp_area(by_id[q], first_place.get(q), r["_iso"], area_names.get(q), r.get("location"))]
    titles = sorted({t for r in need for s in r["_segs"] for t in title_candidates(s, r["_cname"])})
    tq = wp.titles_to_qids("en", titles)
    places = wp.place_info([q for q in tq.values() if q])
    ctx["places"].update(places)

    def geocode(rec: dict[str, Any]) -> list[dict[str, Any]]:
        found = []
        for seg in rec["_segs"]:
            for t in title_candidates(seg, rec["_cname"]):
                q = tq.get(wp.clean_title(t))
                p = places.get(q) if q else None
                if wp.usable(p) and p["kind"] not in ("country", "structure") and \
                        (not rec["_iso"] or not p.get("iso2") or p["iso2"] == rec["_iso"]):
                    if p not in found:
                        found.append(p)
                    break
        return found

    def country_place(rec: dict[str, Any]) -> list[dict[str, Any]]:
        if not rec["_iso"]:
            return []
        c = ctx["by_code"].get(rec["_iso"])
        p = ctx["places"].get(c["qid"]) if c else None
        if not wp.usable(p) and c and c.get("coord"):
            p = {"qid": c["qid"], "label": c.get("label"), "lat": c["coord"][0], "lon": c["coord"][1],
                 "country_qid": c["qid"], "iso2": c["iso2"], "kind": "country", "retrieved_at": None}
        return [p] if wp.usable(p) else []

    def set_area(k: dict[str, Any], pls: list[dict[str, Any]], rec: dict[str, Any]) -> None:
        replace_area(out, k, pls, rec["url"], "murderpedia", area_conf, place_record)

    def mp_block(rec: dict[str, Any]) -> dict[str, Any]:
        # „Status”, „Characteristics” și „Victim profile” pot conține nume de victime (principiul 6):
        # se folosesc doar intern (statut juridic, etichete), nu se publică
        method = rec.get("method")
        return {"url": rec["url"], "classification": rec.get("classification"),
                "method": method if method and len(method) <= 100 else None,
                "location": rec.get("location"), "has_photos": rec.get("has_photos")}

    upgraded = 0
    for q, rec in matched.items():
        k = by_id[q]
        k["links"]["murderpedia"] = rec["url"]
        if rec.get("_type") and rec["_type"] not in k.get("type", []):
            k["type"] = [*k.get("type", []), rec["_type"]]
        k["murderpedia"] = mp_block(rec)
        if rec.get("classification"):
            k["classification"] = [rec["classification"]]
            k["sources"]["classification"] = "murderpedia"
        k["method"] = list(dict.fromkeys(k["method"] + categories.methods(rec.get("method"))))
        k["victim_types"] = list(dict.fromkeys(k["victim_types"] + victim_types_mp(rec)))
        if not k["victims"]:
            v = parse_victims(rec.get("victims"))
            if v:
                k["victims"] = {kk: v[kk] for kk in ("proven", "possible", "note")}
                k["sources"]["victims"] = "murderpedia"
        if not k["active"]:
            ys = [y for y in map(int, re.findall(r"(?<!\d)(1[5-9]\d\d|20[0-2]\d)(?!\d)", rec.get("date_of_murder") or ""))]
            if ys:
                k["active"] = {"start": str(min(ys)), "end": str(max(ys))}
                k["sources"]["active"] = "murderpedia"
        if not k["legal_status"]:
            k["legal_status"] = legal_from_mp(rec)
            if k["legal_status"]:
                k["sources"]["legal_status"] = "murderpedia"
        if needs_mp_area(k, first_place.get(q), rec["_iso"], area_names.get(q), rec.get("location")):
            pls = geocode(rec)
            # nu „rafinăm” spre ceva mai vag: păstrăm Murderpedia doar dacă dă cel puțin la fel de precis
            prev = k["coverage"]["active_area_precision"]
            if pls and prev == "admin1" and k["sources"].get("active_area") == "wikipedia-infobox" and                     all(wp.PRECISION[p["kind"]] == "admin1" for p in pls):
                pls = []
            if pls:
                set_area(k, pls[:15], rec)
                upgraded += 1

    added = 0
    for rec in new:
        name = (rec.get("title") or "").split("|")[0].strip() or rec.get("index_name") or rec["url"]
        kid = "MP-" + hashlib.sha1(rec["url"].encode()).hexdigest()[:10]
        birth = _date_iso(rec.get("date_of_birth"))
        ys = [int(y) for y in re.findall(r"(?<!\d)(1[5-9]\d\d|20[0-2]\d)(?!\d)", rec.get("date_of_murder") or "")]
        v = parse_victims(rec.get("victims"))
        legal = legal_from_mp(rec)
        k = {
            "id": kid, "slug": f"{names.slugify(name)}-{kid[3:9]}",
            "names": {"primary": name, "aliases": [], "native": None},
            "description": ", ".join(x for x in [rec.get("classification"), rec["_cname"]] if x) or None,
            "sex": None if legal == "unidentified" else rec.get("sex"),
            "type": [rec["_type"]],
            "birth": {"date": birth["date"], "precision": birth["precision"], "place_id": None} if birth else None,
            "death": None, "countries": [rec["_iso"]] if rec["_iso"] else [],
            "active": {"start": str(min(ys)), "end": str(max(ys))} if ys else None,
            "victims": {kk: v[kk] for kk in ("proven", "possible", "note")} if v else None,
            "status": None, "legal_status": legal, "penalty": None,
            "classification": [rec["classification"]] if rec.get("classification") else [],
            "method": categories.methods(rec.get("method")), "victim_types": victim_types_mp(rec),
            "summary": None, "image": None,
            "links": {"wikipedia": None, "wikidata": None, "murderpedia": rec["url"], "killercloud": None,
                      "serialkillersinfo": None},
            "lists": [], "murderpedia": mp_block(rec),
            "sources": {"identity": "murderpedia", "inclusion": f"murderpedia-{rec['_type'].replace('_', '-')}",
                        "victims": "murderpedia" if v else None, "active": "murderpedia" if ys else None,
                        "active_area": None, "legal_status": "murderpedia" if legal else None,
                        "birth_death": "murderpedia" if birth else None, "classification": "murderpedia",
                        "method_victim_types": "keywords: murderpedia"},
            "coverage": {"has_events": False, "event_count": 0, "geocoded_events": 0,
                         "active_area_points": 0, "active_area_precision": None},
            "retrieved_at": None,
        }
        killers.append(k)
        by_id[kid] = k
        pls = geocode(rec) or country_place(rec)
        if pls:
            set_area(k, pls[:15], rec)
        added += 1

    rebuild_index(out)
    result = {**stats, "matched_total": len(matched), "new_serial": added, "area_upgraded": upgraded,
              "ambiguous_pct_of_eligible": round(100 * stats["ambiguous"] / max(stats["serial"] + stats["spree"], 1), 1)}
    log.info("Murderpedia: %s", result)
    return result


def rebuild_index(out: dict[str, Any]) -> None:
    """Indexul hărții (un punct per persoană) din killers + primul punct de zonă."""
    killers = out["killers"]
    for k in killers:
        if k["legal_status"] == "unidentified":  # sexul unui autor neidentificat nu e cunoscut
            k["sex"] = None
            k["image"] = None
    first_area = {}
    for f in out["features"]:
        p = f["properties"]
        if p["kind"] == "active_area" and (p["killer_id"] not in first_area or p["id"] < first_area[p["killer_id"]]["properties"]["id"]):
            first_area[p["killer_id"]] = f
    out["index"][:] = []
    for k in killers:
        f = first_area.get(k["id"])
        if not f:
            continue
        per = k["active"]
        out["index"].append({"type": "Feature", "geometry": f["geometry"], "properties": {
            "id": k["id"], "slug": k["slug"], "name": k["names"]["primary"], "countries": ",".join(k["countries"]),
            "victims": (k["victims"] or {}).get("proven"), "legal": k["legal_status"],
            "precision": f["properties"]["precision"], "place": f["properties"]["place_name"],
            "sex": k["sex"], "from": int(per["start"]) if per else None, "to": int(per["end"]) if per else None,
            "m": ",".join(k["method"]), "vt": ",".join(k["victim_types"]), "img": 1 if k["image"] else 0,
            "type": ",".join(k.get("type") or ["serial_killer"]),
        }})
