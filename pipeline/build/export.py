"""Unește Wikidata + Wikipedia, construiește straturile 1 (active_area) și 2 (birth/death) și exportă.

Ieșiri:
- data/killers.json, data/places.json, data/events.geojson, data/coverage.json, data/countries.json
- site/public/data/: aceleași fișiere + killers-index.geojson (un punct per criminal, pentru hartă)
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import time
from collections import Counter
from typing import Any

from pipeline.config import DATA, SITE_DATA
from pipeline.geocode import wikidata_places as wp
from pipeline.normalize import dates, names
from pipeline.normalize.places import jitter, parse_victims
from pipeline.sources import wikidata, wikipedia

log = logging.getLogger(__name__)

FINE_FIELDS = ["locations", "location", "cities", "city", "states", "state", "region"]
COUNTRY_FIELDS = ["country", "countries"]
MAX_AREA_POINTS = 15
SEX = {"Q6581097": "male", "Q6581072": "female", "Q2449503": "male", "Q1052281": "female"}
MANNER = {"Q8454": "executed", "Q10737": "suicide", "Q149086": "killed"}
SUSPECT_SECTIONS = ("disputed", "unconfirmed", "suspected", "unidentified")


def _today() -> str:
    return time.strftime("%Y-%m-%d")


# ------------------------------------------------------------------ colectare și rezolvare locuri

def collect(refresh: bool = False) -> dict[str, Any]:
    people = wikidata.load_people()
    articles = wikipedia.load_articles()
    entries = wikipedia.load_list_entries()
    country_rows = wp.countries(refresh=refresh)
    by_code = {}
    for c in country_rows:
        for code in c["codes"] | {c["iso2"]}:
            by_code.setdefault(code, c)

    # titluri de rezolvat, pe limbă
    titles: dict[str, set[str]] = {}
    for q, a in articles.items():
        lang = a["lang"]
        for f in FINE_FIELDS + COUNTRY_FIELDS:
            v = a["infobox"].get(f)
            if v:
                titles.setdefault(lang, set()).update(v["titles"] + v["text"])
        titles.setdefault(lang, set()).update(a["lead_links"])
        titles.setdefault(lang, set()).update(a.get("crime_links", []) + a.get("body_links", []))
    for e in entries:
        titles.setdefault("en", set()).update(n for n in e["country_names"] if not n.startswith("code:"))
    title_qid: dict[str, dict[str, str | None]] = {}
    for lang, ts in titles.items():
        title_qid[lang] = wp.titles_to_qids(lang, sorted(ts))

    place_qids: set[str] = set()
    for m in title_qid.values():
        place_qids.update(q for q in m.values() if q)
    for p in people.values():
        for prop in ("P19", "P20", "P27", "P551"):
            place_qids.update(p["claims"].get(prop, []))
    place_qids = {q for q in place_qids if re.fullmatch(r"Q\d+", q)}  # fără „unknown value” (genid)
    places = wp.place_info(sorted(place_qids, key=lambda q: int(q[1:])), refresh=False)
    return {"people": people, "articles": articles, "entries": entries, "title_qid": title_qid,
            "places": places, "by_code": by_code, "countries": country_rows}


# ------------------------------------------------------------------ construire

def _resolve(ctx: dict[str, Any], lang: str, titles: list[str]) -> list[dict[str, Any]]:
    out = []
    m = ctx["title_qid"].get(lang, {})
    for t in titles:
        q = m.get(wp.clean_title(t))
        p = ctx["places"].get(q) if q else None
        if wp.usable(p) and p not in out:
            out.append(p)
    return out


def _country_place(ctx: dict[str, Any], iso2: str) -> dict[str, Any] | None:
    c = ctx["by_code"].get(iso2)
    if not c:
        return None
    p = ctx["places"].get(c["qid"])
    if wp.usable(p):
        return p
    if c.get("coord"):
        return {"qid": c["qid"], "label": c.get("label"), "lat": c["coord"][0], "lon": c["coord"][1],
                "country_qid": c["qid"], "iso2": c["iso2"], "kind": "country", "retrieved_at": _today()}
    return None


def _active_area(ctx: dict[str, Any], person: dict[str, Any], article: dict[str, Any] | None,
                 list_entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str, str | None]:
    """Locurile zonei de activitate + baza („wikipedia-infobox”, „wikipedia-lead”, …) + URL sursă."""
    country_isos: set[str] = set()
    country_places: list[dict[str, Any]] = []
    basis_country = None
    src_country = None
    if article and article["lang"] == "en":
        ib = article["infobox"]
        for f in COUNTRY_FIELDS:
            if ib.get(f):
                for p in _resolve(ctx, "en", ib[f]["titles"] + ib[f]["text"]):
                    if p["kind"] == "country":
                        country_places.append(p)
                        if p.get("iso2"):
                            country_isos.add(p["iso2"])
        if country_places:
            basis_country, src_country = "wikipedia-infobox", article["source_url"]

    def consistent(p: dict[str, Any]) -> bool:
        return not country_isos or not p.get("iso2") or p["iso2"] in country_isos

    # 1. infobox: câmpuri fine (orașe, state, locuri)
    if article and article["lang"] == "en":
        fine: list[dict[str, Any]] = []
        for f in FINE_FIELDS:
            v = article["infobox"].get(f)
            if v:
                for p in _resolve(ctx, "en", v["titles"] + v["text"]):
                    if p["kind"] != "country" and consistent(p) and p not in fine:
                        fine.append(p)
        if fine:
            return fine[:MAX_AREA_POINTS], "wikipedia-infobox", article["source_url"]

    # 2. linkurile geografice din introducere
    if article:
        lead = [p for p in _resolve(ctx, article["lang"], article["lead_links"])
                if p["kind"] != "country" and consistent(p)]
        if lead:
            return lead[:MAX_AREA_POINTS], "wikipedia-lead", article["source_url"]
        # 2b. linkurile din secțiunile despre crime, apoi din restul corpului (fără biografie, proces,
        #     închisoare, media); cele mai des menționate locuri, maxim 5
        m = ctx["title_qid"].get(article["lang"], {})
        for key, how in (("crime_links", "wikipedia-crime-sections"), ("body_links", "wikipedia-body")):
            counts: Counter[str] = Counter()
            found: dict[str, dict[str, Any]] = {}
            for t in article.get(key, []):
                pq = m.get(wp.clean_title(t))
                pl = ctx["places"].get(pq) if pq else None
                if wp.usable(pl) and pl["kind"] != "country" and consistent(pl):
                    counts[pl["qid"]] += 1
                    found.setdefault(pl["qid"], pl)
            if counts:
                order = list(found)
                top = sorted(found, key=lambda q: (-counts[q], order.index(q)))[:5]
                return [found[q] for q in top], how, article["source_url"]
        if not country_places:
            lead_c = [p for p in _resolve(ctx, article["lang"], article["lead_links"]) if p["kind"] == "country"]
            if lead_c:
                country_places, basis_country, src_country = lead_c, "wikipedia-lead", article["source_url"]

    # 3. nivel de țară: infobox / introducere / liste / cetățenie
    if not country_places:
        for e in list_entries:
            for n in e["country_names"]:
                if n.startswith("code:"):
                    c = ctx["by_code"].get(n[5:])
                    p = _country_place(ctx, c["iso2"]) if c else None
                    ps = [p] if p else []
                else:
                    ps = [p for p in _resolve(ctx, "en", [n]) if p["kind"] == "country"]
                for p in ps:
                    if p not in country_places:
                        country_places.append(p)
            if country_places:
                basis_country, src_country = "wikipedia-list", e["source_url"]
                break
    if not country_places:
        for q in person["claims"].get("P27", []):
            p = ctx["places"].get(q)
            if wp.usable(p) and p not in country_places:
                country_places.append(p)
        if country_places:
            basis_country, src_country = "wikidata-citizenship", f"https://www.wikidata.org/wiki/{person['id']}"
    return country_places[:5], basis_country or "none", src_country


def _legal_status(person: dict[str, Any], article: dict[str, Any] | None,
                  list_entries: list[dict[str, Any]]) -> str | None:
    cats = " | ".join(article["categories"]).lower() if article else ""
    ib = article["infobox"] if article else {}
    convicted = bool(person["claims"].get("P1399")) or any(
        ib.get(k) for k in ("convictions", "conviction", "criminal_penalty", "penalty"))
    convicted = convicted or "people convicted of murder" in cats or "convicted" in cats
    if "unidentified serial killers" in cats:
        return "unidentified"
    if convicted:
        return "convicted"
    if "acquitted" in cats:
        return "acquitted"
    if "suspected serial killers" in cats or "alleged" in cats:
        return "suspected"
    if "died before trial" in cats:
        return "deceased_before_trial"
    if list_entries and all(e["section"].lower().startswith(SUSPECT_SECTIONS) for e in list_entries):
        return "suspected"
    return None


def _place_record(p: dict[str, Any]) -> dict[str, Any]:
    return {"id": f"P-{p['qid']}", "name": p.get("label") or p["qid"], "country": p.get("iso2"),
            "lat": round(p["lat"], 5), "lon": round(p["lon"], 5), "precision": wp.precision(p),
            "geocoder": "wikidata", "wikidata": p["qid"], "geocoded_at": p.get("retrieved_at")}


def build(ctx: dict[str, Any]) -> dict[str, Any]:
    people, articles = ctx["people"], ctx["articles"]
    entries_by_q: dict[str, list[dict[str, Any]]] = {}
    for e in ctx["entries"]:
        if e.get("qid"):
            entries_by_q.setdefault(e["qid"], []).append(e)

    killers: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    index: list[dict[str, Any]] = []
    used_places: dict[str, dict[str, Any]] = {}
    slugs: Counter[str] = Counter()
    pending = []
    for q in sorted(people, key=lambda x: int(x[1:])):
        p = people[q]
        c = p["claims"]
        art = articles.get(q)
        name = names.primary_name(c, art["title"] if art else None)
        if not name:
            name = q
        slug = names.slugify(name) or q.lower()
        slugs[slug] += 1
        pending.append((q, p, art, name, slug))

    for q, p, art, name, slug in pending:
        c = p["claims"]
        if slugs[slug] > 1:
            slug = f"{slug}-{q.lower()}"
        lentries = entries_by_q.get(q, [])
        ib = art["infobox"] if art and art["lang"] == "en" else {}
        area, basis, area_src = _active_area(ctx, p, art, lentries)
        birth_t = dates.wikidata_time((c.get("P569") or [None])[0])
        death_t = dates.wikidata_time((c.get("P570") or [None])[0])
        pob = ctx["places"].get((c.get("P19") or [None])[0] or "")
        pod = ctx["places"].get((c.get("P20") or [None])[0] or "")
        wd_url = f"https://www.wikidata.org/wiki/{q}"

        evs = []
        for i, pl in enumerate(area, 1):
            evs.append(("active_area", pl, f"{q}-a{i:02d}", area_src, basis))
        if wp.usable(pob):
            evs.append(("birth", pob, f"{q}-b", wd_url, "wikidata-P19"))
        if wp.usable(pod):
            evs.append(("death", pod, f"{q}-d", wd_url, "wikidata-P20"))
        killer_events = []
        for kind, pl, eid, src, how in evs:
            rec = _place_record(pl)
            used_places[rec["id"]] = rec
            lat, lon = jitter(rec["lat"], rec["lon"], eid, rec["precision"])
            date = None
            if kind == "birth" and birth_t:
                date = {"start": birth_t["date"], "end": birth_t["date"], "precision": birth_t["precision"]}
            if kind == "death" and death_t:
                date = {"start": death_t["date"], "end": death_t["date"], "precision": death_t["precision"]}
            props = {"id": eid, "killer_id": q, "kind": kind, "date": date, "place_id": rec["id"],
                     "place_name": rec["name"], "precision": rec["precision"], "victim_count": None,
                     "victim_label": None, "confidence": 1.0 if how.startswith("wikidata-P") else
                     {"wikipedia-infobox": 0.9, "wikipedia-lead": 0.6, "wikipedia-crime-sections": 0.5,
                      "wikipedia-body": 0.4}.get(how, 0.3),
                     "source_url": src, "source_quote": None, "extraction": how}
            feat = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}
            features.append(feat)
            killer_events.append(feat)

        victims = parse_victims(ib.get("victims"), c.get("P1345"))
        period = dates.active_period(ib.get("begin_year") or ib.get("beginyear"),
                                     ib.get("end_year") or ib.get("endyear"), ib.get("years_active"))
        legal = _legal_status(p, art, lentries)
        manners = [MANNER[m] for m in c.get("P1196", []) if m in MANNER]
        status = manners[0] if manners else ("deceased" if death_t else None)
        countries = []
        for pl in area:
            if pl.get("iso2") and pl["iso2"] not in countries:
                countries.append(pl["iso2"])
        area_events = [f for f in killer_events if f["properties"]["kind"] == "active_area"]
        primary = area_events[0] if area_events else None

        killer = {
            "id": q,
            "slug": slug,
            "names": {"primary": name, "aliases": (c.get("alias") or [])[:6], "native": None},
            "description": (c.get("description") or [None])[0],
            "sex": next((SEX[s] for s in c.get("P21", []) if s in SEX), None),
            "birth": {"date": birth_t["date"] if birth_t else None,
                      "precision": birth_t["precision"] if birth_t else None,
                      "place_id": f"P-{pob['qid']}" if wp.usable(pob) else None} if (birth_t or wp.usable(pob)) else None,
            "death": {"date": death_t["date"] if death_t else None,
                      "precision": death_t["precision"] if death_t else None,
                      "place_id": f"P-{pod['qid']}" if wp.usable(pod) else None,
                      "cause": status if status in ("executed", "suicide", "killed") else None}
            if (death_t or wp.usable(pod)) else None,
            "countries": countries,
            "active": period,
            "victims": {k: victims[k] for k in ("proven", "possible", "note")} if victims else None,
            "status": status,
            "legal_status": legal,
            "penalty": ib.get("penalty") or ib.get("criminal_penalty"),
            "classification": [],
            "method": [],
            "summary": {"text": art["summary"], "license": "CC BY-SA 4.0", "source_url": art["source_url"],
                        "attribution": f"Wikipedia contributors, “{art['title']}”"}
            if art and art.get("summary") else None,
            "image": None,  # faza 4: doar Commons cu licență verificată
            "links": {"wikipedia": art["url"] if art else None, "wikidata": wd_url, "murderpedia": None,
                      "killercloud": None, "serialkillersinfo": None},
            "lists": sorted({e["list"] for e in lentries}),
            "sources": {
                "identity": "wikidata",
                "inclusion": "wikidata-occupation" if p.get("origin") == "wikidata-sparql" else "wikipedia-list",
                "victims": victims["source"] if victims else None,
                "active": "wikipedia-infobox" if period else None,
                "active_area": basis,
                "legal_status": "wikidata+wikipedia-categories" if legal else None,
                "birth_death": "wikidata",
            },
            "coverage": {"has_events": False, "event_count": 0, "geocoded_events": 0,
                         "active_area_points": len(area_events),
                         "active_area_precision": primary["properties"]["precision"] if primary else None},
            "retrieved_at": max(filter(None, [p.get("retrieved_at"), art.get("retrieved_at") if art else None])),
        }
        killers.append(killer)
        if primary:
            index.append({"type": "Feature", "geometry": primary["geometry"], "properties": {
                "id": q, "slug": slug, "name": name, "countries": ",".join(countries),
                "victims": victims["proven"] if victims else None, "legal": legal,
                "precision": primary["properties"]["precision"], "place": primary["properties"]["place_name"],
            }})
    return {"killers": killers, "features": features, "index": index, "places": used_places}


def coverage(ctx: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    killers = out["killers"]
    n = len(killers)
    prec = Counter(k["coverage"]["active_area_precision"] or "none" for k in killers)
    fine = sum(v for k, v in prec.items() if k in ("address", "city", "county", "admin1"))
    basis = Counter(k["sources"]["active_area"] for k in killers)
    entries = ctx["entries"]
    return {
        "generated_at": _today(),
        "killers_total": n,
        "sources": {
            "wikidata_sparql_items": sum(1 for p in ctx["people"].values() if p.get("origin") == "wikidata-sparql"),
            "added_from_wikipedia_lists": sum(1 for p in ctx["people"].values() if p.get("origin") == "wikipedia-list"),
            "wikipedia_list_entries": len(entries),
            "wikipedia_list_unique_titles": len({e["title"] for e in entries}),
            "wikipedia_list_titles_with_qid": len({e["title"] for e in entries if e.get("qid")}),
            "lists": sorted({e["list"] for e in entries}),
        },
        "articles": {
            "with_any_wikipedia_article": sum(1 for k in killers if k["links"]["wikipedia"]),
            "with_english_article": sum(1 for k in killers if (k["links"]["wikipedia"] or "").startswith("https://en.")),
        },
        "active_area": {
            "with_any_point": sum(1 for k in killers if k["coverage"]["active_area_points"]),
            "at_admin1_or_finer": fine,
            "pct_at_admin1_or_finer": round(100 * fine / n, 1) if n else 0,
            "by_precision": dict(prec.most_common()),
            "by_basis": dict(basis.most_common()),
        },
        "birth_place_geocoded": sum(1 for k in killers if k["birth"] and k["birth"]["place_id"]),
        "death_place_geocoded": sum(1 for k in killers if k["death"] and k["death"]["place_id"]),
        "legal_status": dict(Counter(k["legal_status"] or "undetermined" for k in killers).most_common()),
        "with_victim_count": sum(1 for k in killers if k["victims"]),
        "countries_with_killers": len({c for k in killers for c in k["countries"]}),
        "events": dict(Counter(f["properties"]["kind"] for f in out["features"]).most_common()),
        "events_layer3_murders": 0,
        "places": len(out["places"]),
        "not_yet_included": ["Murderpedia (faza 2)", "locațiile individuale ale crimelor (faza 3)"],
    }


def _write(path, obj, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) if compact else \
        json.dumps(obj, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def run() -> None:
    ctx = collect()
    out = build(ctx)
    cov = coverage(ctx, out)
    country_names = {c["iso2"]: c.get("label") or c["iso2"] for c in ctx["countries"]}
    counts = Counter(c for k in out["killers"] for c in k["countries"])
    countries = [{"code": code, "name": country_names.get(code, code), "killers": n}
                 for code, n in sorted(counts.items(), key=lambda kv: country_names.get(kv[0], kv[0]))]
    killers = sorted(out["killers"], key=lambda k: k["id"] and int(k["id"][1:]))
    places = sorted(out["places"].values(), key=lambda p: int(p["id"][3:]))
    files = {
        "killers.json": killers,
        "places.json": places,
        "events.geojson": {"type": "FeatureCollection", "features": out["features"]},
        "killers-index.geojson": {"type": "FeatureCollection", "features": out["index"]},
        "countries.json": countries,
    }
    for name, obj in files.items():
        _write(DATA / name, obj)
    _write(DATA / "coverage.json", cov, compact=False)
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    for name in [*files, "coverage.json"]:
        shutil.copyfile(DATA / name, SITE_DATA / name)
    a = cov["active_area"]
    log.info("Export: %d criminali, %d evenimente, %d locuri; zonă de activitate ≤ admin1: %d (%.1f%%)",
             cov["killers_total"], len(out["features"]), len(places), a["at_admin1_or_finer"],
             a["pct_at_admin1_or_finer"])
