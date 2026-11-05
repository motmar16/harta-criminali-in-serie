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
from pipeline.config import RAW
from pipeline.normalize import categories, dates, names
from pipeline.normalize.places import jitter, parse_victims
from pipeline.sources import wikidata, wikipedia

log = logging.getLogger(__name__)

FINE_FIELDS = ["locations", "location", "cities", "city", "states", "state", "region"]
COUNTRY_FIELDS = ["country", "countries"]
MAX_AREA_POINTS = 15
# state dispărute -> statele de azi de pe teritoriul lor (o crimă „în URSS” poate fi în Rusia, Ucraina…)
SUCCESSORS = {
    "SU": {"RU", "UA", "BY", "KZ", "UZ", "GE", "AZ", "LT", "MD", "LV", "KG", "TJ", "AM", "TM", "EE"},
    "YU": {"RS", "HR", "SI", "BA", "MK", "ME", "XK"},
    "CS": {"CZ", "SK", "RS", "ME"},
    "DD": {"DE"},
}
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
        titles.setdefault(lang, set()).update(a.get("crime_links", []) + a.get("body_links", [])
                                              + a.get("crime_sentence_links", []))
        for lang2, ls in (a.get("other_crime_links") or {}).items():
            titles.setdefault(lang2, set()).update(ls)
    for e in entries:
        titles.setdefault("en", set()).update(n for n in e["country_names"] if not n.startswith("code:"))
        titles.setdefault("en", set()).update(e.get("text_links", []))
    radford_by_q = _match_radford(people, articles)
    for r in radford_by_q.values():
        titles.setdefault("en", set()).update(r["places"])
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
    # evenimente legate din introducere / propozițiile despre crime („[[Columbine High School massacre]]”)
    event_q: set[str] = set()
    for a in articles.values():
        m = title_qid.get(a["lang"], {})
        for t in a["lead_links"] + a.get("crime_sentence_links", []):
            if wp.EVENT_TITLE.search(t):
                q = m.get(wp.clean_title(t))
                if q:
                    event_q.add(q)
    events = wp.event_info(event_q)
    for e in events.values():
        place_qids.update(e["loc"] + e["admin"])
    places = wp.place_info(sorted(place_qids, key=lambda q: int(q[1:])), refresh=False)
    img_path = RAW / "commons" / "images.json"
    images = json.loads(img_path.read_text(encoding="utf-8")) if img_path.exists() else {}
    return {"people": people, "articles": articles, "entries": entries, "title_qid": title_qid, "images": images,
            "radford": radford_by_q, "events": events,
            "places": places, "by_code": by_code, "countries": country_rows}


def _match_radford(people: dict[str, Any], articles: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Cronologiile Radford -> QID, după nume normalizat (etichete Wikidata, alias-uri, titlul articolului)."""
    from pipeline.normalize import dedupe
    from pipeline.sources import radford
    recs = radford.load()
    if not recs:
        return {}
    by_name: dict[str, set[str]] = {}
    for q, p in people.items():
        names = [v for k, vals in p["claims"].items() if k.startswith("label:") or k == "alias" for v in vals]
        if articles.get(q):
            names.append(articles[q]["title"])
        for n in names:
            nn = dedupe.norm(n)
            if nn:
                by_name.setdefault(nn, set()).add(q)
                toks = nn.split()
                if len(toks) > 2:  # „John Eric Armstrong” -> și „john armstrong”
                    by_name.setdefault(f"{toks[0]} {toks[-1]}", set()).add(q)
    from rapidfuzz import fuzz
    by_surname: dict[str, set[str]] = {}
    for nn, qs in by_name.items():
        by_surname.setdefault(nn.split()[-1], set()).update((nn, q) for q in qs)
    out = {}
    for r in recs:
        target = dedupe.norm(r["name"])
        hits = by_name.get(target, set())
        if not hits and target:
            # aceeași familie + prenume asemănător („Judias Buenoano” ~ „Judy Buenoano”); un singur candidat
            cands = {q for nn, q in by_surname.get(target.split()[-1], set()) if fuzz.token_sort_ratio(nn, target) >= 80}
            hits = cands
        if len(hits) == 1:
            out[next(iter(hits))] = r
    log.info("Radford: %d din %d cronologii potrivite cu persoane", len(out), len(recs))
    return out


def _ranked(ctx: dict[str, Any], pairs: list[tuple[str, str]], ok) -> list[dict[str, Any]]:
    """Locurile cele mai des menționate (lang, titlu), din țara dominantă, maxim 5."""
    counts: Counter[str] = Counter()
    found: dict[str, dict[str, Any]] = {}
    for lang, t in pairs:
        pq = ctx["title_qid"].get(lang, {}).get(wp.clean_title(t))
        pl = ctx["places"].get(pq) if pq else None
        if wp.usable(pl) and pl["kind"] not in ("country", "structure") and ok(pl):
            counts[pl["qid"]] += 1
            found.setdefault(pl["qid"], pl)
    if not counts:
        return []
    order = list(found)
    top = _dominant_country(sorted(found, key=lambda q: (-counts[q], order.index(q))), found)[:5]
    return [found[q] for q in top]


# ------------------------------------------------------------------ construire

def _resolve(ctx: dict[str, Any], lang: str, titles: list[str]) -> list[dict[str, Any]]:
    """Locuri folosibile pentru zona de activitate. Clădirile (închisori, tribunale, spitale) se exclud:
    în texte apar mai ales ca locuri de detenție sau proces, nu ale crimelor."""
    out = []
    m = ctx["title_qid"].get(lang, {})
    for t in titles:
        q = m.get(wp.clean_title(t))
        p = ctx["places"].get(q) if q else None
        if wp.usable(p) and p["kind"] != "structure" and p not in out:
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

    allowed = set(country_isos)
    for iso in country_isos:
        allowed |= SUCCESSORS.get(iso, set())

    def consistent(p: dict[str, Any]) -> bool:
        return not country_isos or not p.get("iso2") or p["iso2"] in allowed

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
            # rafinare: infobox-ul dă doar 1–2 state, iar cronologia Radford numește orașe din ele
            rad = ctx["radford"].get(person["id"])
            if rad and len(fine) <= 2 and all(p["kind"] in ("admin1", "region", "admin_other") for p in fine):
                names = {(p.get("label") or "").lower() for p in fine}
                cities = _ranked(ctx, [("en", t) for t in rad["places"] if t.split(", ")[-1].lower() in names],
                                 consistent)
                if cities:
                    return cities, "radford", rad["url"]
            return fine[:MAX_AREA_POINTS], "wikipedia-infobox", article["source_url"]

    # 1a'. articolul evenimentului (masacru, atac, serie de crime) legat din introducere/propoziții:
    #      locația lui din Wikidata (P276 loc, apoi P131 unitate administrativă, apoi coordonatele P625)
    if article:
        m = ctx["title_qid"].get(article["lang"], {})
        ev_places: list[dict[str, Any]] = []
        for t in article["lead_links"] + article.get("crime_sentence_links", []):
            if not wp.EVENT_TITLE.search(t):
                continue
            ev = ctx["events"].get(m.get(wp.clean_title(t)) or "")
            if not ev:
                continue
            pl = None
            for cand in ev["loc"] + ev["admin"]:
                p = ctx["places"].get(cand)
                if wp.usable(p) and p["kind"] != "country":
                    pl = p
                    break
            if pl is None and ev["coord"]:
                pl = {"qid": ev["qid"], "label": ev["label"] or t, "lat": ev["coord"][0], "lon": ev["coord"][1],
                      "country_qid": None, "iso2": None, "kind": "structure", "retrieved_at": _today()}
            if pl and consistent(pl) and pl not in ev_places:
                ev_places.append(pl)
                # doar primul eveniment (cel din introducere, de regulă al persoanei); restul pot fi
                # atacuri menționate ca termen de comparație („ca la Utøya”)
                break
        if ev_places:
            return ev_places, "wikidata-event", article["source_url"]

    # 1a. cronologia Radford (locurile din rândurile despre crime)
    rad = ctx["radford"].get(person["id"])
    if rad:
        pls = _ranked(ctx, [("en", t) for t in rad["places"]], consistent)
        if pls:
            return pls, "radford", rad["url"]

    # 1b. linkurile din propozițiile despre crime (orice limbă, orice secțiune); cele mai frecvente, maxim 5
    if article and article.get("crime_sentence_links"):
        m = ctx["title_qid"].get(article["lang"], {})
        counts: Counter[str] = Counter()
        found: dict[str, dict[str, Any]] = {}
        for t in article["crime_sentence_links"]:
            pq = m.get(wp.clean_title(t))
            pl = ctx["places"].get(pq) if pq else None
            if wp.usable(pl) and pl["kind"] not in ("country", "structure") and consistent(pl):
                counts[pl["qid"]] += 1
                found.setdefault(pl["qid"], pl)
        if counts:
            order = list(found)
            top = _dominant_country(sorted(found, key=lambda q: (-counts[q], order.index(q))), found)[:5]
            return [found[q] for q in top], "wikipedia-crime-sentences", article["source_url"]

    # 1c. propozițiile despre crime din articolele în alte limbi (doar pentru locațiile slabe din build-ul anterior)
    if article and article.get("other_crime_links"):
        pls = _ranked(ctx, [(l, t) for l, ts in article["other_crime_links"].items() for t in ts], consistent)
        if pls:
            return pls, "wikipedia-other-languages", article["source_url"]

    # 1d. linkurile din textul intrării în listele Wikipedia („killed … in [[Kabul]]”)
    lt = [("en", t) for e in list_entries for t in e.get("text_links", [])]
    if lt:
        pls = _ranked(ctx, lt, consistent)
        if pls:
            return pls, "wikipedia-list-text", list_entries[0]["source_url"]

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
                if wp.usable(pl) and pl["kind"] not in ("country", "structure") and consistent(pl):
                    counts[pl["qid"]] += 1
                    found.setdefault(pl["qid"], pl)
            if counts:
                order = list(found)
                top = _dominant_country(sorted(found, key=lambda q: (-counts[q], order.index(q))), found)[:5]
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


def _dominant_country(ranked: list[str], found: dict[str, dict[str, Any]]) -> list[str]:
    """Păstrează doar locurile din țara celui mai menționat loc. Textele enumeră uneori cazuri similare
    din alte țări; zona unei persoane e rareori împrăștiată pe mai multe continente."""
    if not ranked:
        return ranked
    iso = found[ranked[0]].get("iso2")
    return [q for q in ranked if not iso or found[q].get("iso2") in (iso, None)]


def _legal_status(person: dict[str, Any], article: dict[str, Any] | None,
                  list_entries: list[dict[str, Any]]) -> str | None:
    if person.get("origin") == "wikipedia-category-case":
        return "unidentified"
    cats = " | ".join(article["categories"]).lower() if article else ""
    ib = article["infobox"] if article else {}
    convicted = bool(person["claims"].get("P1399")) or any(
        ib.get(k) for k in ("convictions", "conviction", "criminal_penalty", "penalty"))
    convicted = convicted or "people convicted of murder" in cats or "convicted" in cats
    if re.search(r"unidentified [^|]*(?:serial killers|murderers|killers)", cats) or             "unidentified" in (person.get("category") or "").lower():
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
    # o persoană al cărei articol e articolul comun al unui duo („Eric Harris and Dylan Klebold”)
    # se contopește în intrarea duo-ului, ca să nu apară de două ori în același loc
    group_titles = {articles[q]["title"] for q, p in people.items()
                    if p.get("origin") == "wikipedia-category-group" and articles.get(q)}
    for q in sorted(people, key=lambda x: int(x[1:])):
        p = people[q]
        c = p["claims"]
        art = articles.get(q)
        if art and art["title"] in group_titles and p.get("origin") != "wikipedia-category-group":
            continue
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
                     {"wikipedia-infobox": 0.9, "wikidata-event": 0.9, "radford": 0.8, "wikipedia-crime-sentences": 0.7, "wikipedia-other-languages": 0.65,
                      "wikipedia-list-text": 0.6, "wikipedia-lead": 0.6, "wikipedia-crime-sections": 0.5,
                      "wikipedia-body": 0.4}.get(how, 0.3),
                     "source_url": src, "source_quote": None, "extraction": how}
            feat = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}
            features.append(feat)
            killer_events.append(feat)

        victims = parse_victims(ib.get("victims"), c.get("P1345"))
        period = dates.active_period(ib.get("begin_year") or ib.get("beginyear"),
                                     ib.get("end_year") or ib.get("endyear"), ib.get("years_active"))
        legal = _legal_status(p, art, lentries)
        if not legal and "suspected" in (p.get("category") or "").lower():
            legal = "suspected"
        hints = categories.wiki_category_hints(art["categories"]) if art else ""
        desc = (c.get("description") or [None])[0]
        meth = categories.methods(hints, ib.get("weapons"))
        vtypes = categories.victim_types(hints, desc)
        image = ctx["images"].get(q) if legal != "unidentified" else None
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
            # la autorii neidentificați sexul nu e cunoscut, chiar dacă Wikidata are o valoare (ex. „male”)
            "sex": None if legal == "unidentified" else next((SEX[s] for s in c.get("P21", []) if s in SEX), None),
            "type": p.get("types") or ["serial_killer"],
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
            "method": meth,
            "victim_types": vtypes,
            "summary": {"text": art["summary"], "license": "CC BY-SA 4.0", "source_url": art["source_url"],
                        "attribution": f"Wikipedia contributors, “{art['title']}”"}
            if art and art.get("summary") else None,
            "image": image,  # doar Wikimedia Commons (P18) cu licență liberă verificată
            "links": {"wikipedia": art["url"] if art else None, "wikidata": wd_url, "murderpedia": None,
                      "radford": ctx["radford"][q]["url"] if q in ctx["radford"] else None,
                      "killercloud": None, "serialkillersinfo": None},
            "lists": sorted({e["list"] for e in lentries}),
            "sources": {
                "identity": "wikidata",
                "inclusion": {"wikidata-sparql": "wikidata-occupation", "wikipedia-list": "wikipedia-list",
                              "wikipedia-category": "wikipedia-category",
                              "wikipedia-category-case": "wikipedia-category-case",
                              "wikipedia-category-group": "wikipedia-category-group"}.get(p.get("origin"), p.get("origin")),
                "victims": victims["source"] if victims else None,
                "method_victim_types": "keywords: wikipedia-categories+infobox" if (meth or vtypes) else None,
                "image": "wikimedia-commons" if image else None,
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
                "sex": killer["sex"], "from": int(period["start"]) if period else None,
                "to": int(period["end"]) if period else None,
                "m": ",".join(meth), "vt": ",".join(vtypes), "img": 1 if image else 0,
                "type": ",".join(killer["type"]),
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
        "with_murderpedia_link": sum(1 for k in killers if k["links"].get("murderpedia")),
        "by_inclusion": dict(Counter(k["sources"]["inclusion"] for k in killers).most_common()),
        "with_photo": sum(1 for k in killers if k.get("image")),
        "with_method": sum(1 for k in killers if k.get("method")),
        "with_victim_types": sum(1 for k in killers if k.get("victim_types")),
        "not_yet_included": ["locațiile individuale ale crimelor (faza 3)"],
    }


def _apply_corrections(out: dict[str, Any]) -> int:
    """Corecturi manuale de locație (data/validare/, vezi pipeline/build/qa.py); au prioritate maximă.
    Valori: titluri Wikipedia engleză sau QID-uri Wikidata; „ok” = locația automată a fost verificată."""
    from pipeline.build import murderpedia_merge, qa
    fixes = qa.load_corrections()
    if not fixes:
        return 0
    titles = [t for ts in fixes.values() for t in ts if t != "ok" and not re.fullmatch(r"Q[0-9]+", t)]
    tq = wp.titles_to_qids("en", titles)
    qids = [q for q in tq.values() if q] + [t for ts in fixes.values() for t in ts if re.fullmatch(r"Q[0-9]+", t)]
    places = wp.place_info(qids)
    by_id = {k["id"]: k for k in out["killers"]}
    n = 0
    for kid, vals in fixes.items():
        k = by_id.get(kid)
        if not k:
            log.warning("Corectură pentru un id necunoscut: %s", kid)
            continue
        if vals == ["ok"]:
            k["sources"]["active_area_verified"] = "manual"  # sursa automată rămâne, dar e confirmată de om
            n += 1
            continue
        pls = []
        for v in vals:
            q = v if re.fullmatch(r"Q[0-9]+", v) else tq.get(wp.clean_title(v))
            if q and wp.usable(places.get(q)):
                pls.append(places[q])
            else:
                log.warning("Corectură %s: „%s” nu e un loc recunoscut (titlu Wikipedia engleză sau Q-ID)", kid, v)
        if pls:
            murderpedia_merge.replace_area(out, k, pls, "data/validare/locatii_corectii.csv", "manual", 1.0,
                                           _place_record)
            n += 1
    return n


def _write(path, obj, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) if compact else \
        json.dumps(obj, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def run() -> None:
    ctx = collect()
    out = build(ctx)
    from pipeline.build import murderpedia_merge
    mp_stats = murderpedia_merge.merge(ctx, out, _place_record)
    applied = _apply_corrections(out)
    murderpedia_merge.rebuild_index(out)
    from pipeline.build import qa
    cmap = murderpedia_merge._country_map(ctx["countries"])
    qa_stats = qa.report(out["killers"], out["features"],
                         mp_iso=lambda loc: murderpedia_merge.split_location(loc, cmap)[0])
    cov = coverage(ctx, out)
    cov["murderpedia"] = mp_stats
    cov["location_qa"] = {**qa_stats, "manual_corrections_applied": applied}
    country_names = {c["iso2"]: c.get("label") or c["iso2"] for c in ctx["countries"]}
    counts = Counter(c for k in out["killers"] for c in k["countries"])
    countries = [{"code": code, "name": country_names.get(code, code), "killers": n}
                 for code, n in sorted(counts.items(), key=lambda kv: country_names.get(kv[0], kv[0]))]
    killers = sorted(out["killers"], key=lambda k: (0, int(k["id"][1:]), "") if k["id"].startswith("Q") else (1, 0, k["id"]))
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
