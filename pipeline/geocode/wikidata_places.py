"""Rezolvarea locurilor prin Wikidata, cu cache SQLite commit-at (pipeline/geocode/cache.sqlite).

- titlu Wikipedia -> QID (MediaWiki pageprops, urmează redirecturile)
- QID -> coordonate (P625), țară (P17 -> P297), tip de loc (clasa P31/P279*) -> precizie

Precizie: `city` (așezare umană), `county` (subdiviziune de nivel 2), `admin1` (nivel 1 sau regiune),
`country` (stat). Item-urile care nu sunt locuri (persoane, concepte) primesc kind = NULL și sunt ignorate.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any, Iterable

from pipeline import http
from pipeline.config import GEOCODE_CACHE
from pipeline.sources import mediawiki
from pipeline.sources.wikidata import sparql

log = logging.getLogger(__name__)

# clasă Wikidata -> tip; prioritatea e în KIND_ORDER (cel mai fin câștigă)
CLASSES = {
    "Q486972": "settlement",   # human settlement (include oraș, sat)
    "Q123705": "settlement",   # neighbourhood
    "Q15284": "settlement",    # municipality (comune, Gemeinde: nu sunt „human settlement” în Wikidata)
    "Q41176": "structure",     # building
    "Q811979": "structure",    # architectural structure
    "Q13220204": "admin2",     # second-level administrative country subdivision
    "Q13221722": "admin2",     # third-level administrative country subdivision
    "Q47168": "admin2",        # county of the United States
    "Q10864048": "admin1",     # first-level administrative country subdivision
    "Q35657": "admin1",        # U.S. state
    "Q107390": "admin1",       # federated state
    "Q56061": "admin_other",   # administrative territorial entity (nivel necunoscut)
    "Q6256": "country",        # country
    "Q3624078": "country",     # sovereign state
    "Q3024240": "country",     # historical country
    "Q236036": "country",      # republică unională sovietică (RSFSR etc.): prea mare pentru „admin1”
    "Q1620908": "region",      # historical region
    "Q82794": "region",        # geographic region
    "Q43229": "org",           # organization (doar ca filtru negativ)
}
SOCIALIST_REPUBLIC = re.compile(r"Soviet (?:Federative )?Socialist Republic|^Socialist (?:Federal )?Republic of", re.I)
KIND_ORDER = ["settlement", "structure", "admin2", "admin1", "admin_other", "country", "region"]
PRECISION = {"settlement": "city", "structure": "address", "admin2": "county", "admin1": "admin1",
             "admin_other": "admin1", "region": "admin1", "country": "country"}
PRECISION_RANK = {"address": 0, "city": 1, "county": 2, "admin1": 3, "country": 4}

PLACE_QUERY = """
SELECT ?pl ?label ?coord ?ownIso ?country ?iso ?cls WHERE {
  VALUES ?pl { %s }
  OPTIONAL { ?pl rdfs:label ?label . FILTER(LANG(?label) = "en") }
  OPTIONAL { ?pl wdt:P625 ?coord }
  OPTIONAL { ?pl wdt:P297 ?ownIso }
  OPTIONAL { ?pl wdt:P17 ?country . OPTIONAL { ?country wdt:P297 ?iso } }
  OPTIONAL { ?pl wdt:P31/wdt:P279* ?cls . hint:Prior hint:gearing "forward" . FILTER(?cls IN (%s)) }
}
"""

COUNTRIES_QUERY = """
SELECT ?c ?label ?iso2 ?iso3 ?ioc ?coord WHERE {
  ?c wdt:P297 ?iso2 .
  OPTIONAL { ?c rdfs:label ?label . FILTER(LANG(?label) = "en") }
  OPTIONAL { ?c wdt:P298 ?iso3 }
  OPTIONAL { ?c wdt:P984 ?ioc }
  OPTIONAL { ?c wdt:P625 ?coord }
}
"""

_db: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _db
    if _db is None:
        GEOCODE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(GEOCODE_CACHE)
        _db.executescript("""
        CREATE TABLE IF NOT EXISTS title_qid (lang TEXT, title TEXT, qid TEXT, retrieved_at TEXT,
                                              PRIMARY KEY (lang, title));
        CREATE TABLE IF NOT EXISTS place (qid TEXT PRIMARY KEY, label TEXT, lat REAL, lon REAL,
                                          country_qid TEXT, iso2 TEXT, kind TEXT, retrieved_at TEXT);
        """)
    return _db


def _batches(items: list[str], n: int) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _point(wkt: str) -> tuple[float, float] | None:
    m = re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", wkt)
    return (float(m.group(2)), float(m.group(1))) if m else None


def clean_title(t: str) -> str:
    t = t.split("#", 1)[0].replace("_", " ").strip().lstrip(":")
    t = re.sub(r"\s+", " ", t)
    return t[:1].upper() + t[1:] if t else t


def titles_to_qids(lang: str, titles: Iterable[str]) -> dict[str, str | None]:
    titles = [t for t in dict.fromkeys(clean_title(t) for t in titles) if t and len(t) < 250]
    con = db()
    out: dict[str, str | None] = {}
    todo = []
    for t in titles:
        row = con.execute("SELECT qid FROM title_qid WHERE lang=? AND title=?", (lang, t)).fetchone()
        if row is None:
            todo.append(t)
        else:
            out[t] = row[0]
    if todo:
        log.info("%s: rezolv %d titluri -> QID", lang, len(todo))
    for batch in _batches(todo, 50):
        res = mediawiki.resolve_qids(lang, batch)
        for t in batch:
            out[t] = res.get(t)
            con.execute("INSERT OR REPLACE INTO title_qid VALUES (?,?,?,?)", (lang, t, out[t], http.today()))
        con.commit()
    return out


def place_info(qids: Iterable[str], refresh: bool = False) -> dict[str, dict[str, Any]]:
    qids = [q for q in dict.fromkeys(qids) if q and re.fullmatch(r"Q\d+", q)]
    con = db()
    todo = qids if refresh else [q for q in qids
                                 if con.execute("SELECT 1 FROM place WHERE qid=?", (q,)).fetchone() is None]
    if todo:
        log.info("Wikidata: informații de loc pentru %d item-uri", len(todo))
    cls_values = ", ".join(f"wd:{c}" for c in CLASSES)
    for n, batch in enumerate(_batches(todo, 80)):
        bindings, retrieved = _place_bindings(batch, cls_values, refresh)
        acc: dict[str, dict[str, Any]] = {q: {"kinds": set()} for q in batch}
        for b in bindings:
            q = b["pl"]["value"].rsplit("/", 1)[-1]
            a = acc[q]
            if "label" in b:
                a.setdefault("label", b["label"]["value"])
            if "coord" in b and "coord" not in a:
                pt = _point(b["coord"]["value"])
                if pt:
                    a["coord"] = pt
            if "ownIso" in b:
                a["own_iso"] = b["ownIso"]["value"]
            if "country" in b:
                cq = b["country"]["value"].rsplit("/", 1)[-1]
                # preferăm o țară cu cod ISO (P17 poate avea și state istorice)
                if "iso" in b and not a.get("iso"):
                    a["country"], a["iso"] = cq, b["iso"]["value"]
                a.setdefault("country", cq)
            if "cls" in b:
                a["kinds"].add(CLASSES[b["cls"]["value"].rsplit("/", 1)[-1]])
        for q, a in acc.items():
            if a.get("own_iso"):
                kind = "country"
            else:
                kind = next((k for k in KIND_ORDER if k in a["kinds"]), None)
                # organizațiile prinse doar ca „region” (ex. ministere) nu sunt locuri
                if kind == "region" and "org" in a["kinds"]:
                    kind = None
            if kind == "country":
                a["country"], a["iso"] = q, a.get("own_iso")
            lat, lon = a.get("coord", (None, None))
            con.execute("INSERT OR REPLACE INTO place VALUES (?,?,?,?,?,?,?,?)",
                        (q, a.get("label"), lat, lon, a.get("country"), a.get("iso"), kind, retrieved))
        con.commit()
        if n % 10 == 9:
            log.info("  … %d/%d", (n + 1) * 80, len(todo))
    out = {}
    for q in qids:
        row = con.execute("SELECT qid,label,lat,lon,country_qid,iso2,kind,retrieved_at FROM place WHERE qid=?",
                          (q,)).fetchone()
        if row:
            p = dict(zip(["qid", "label", "lat", "lon", "country_qid", "iso2", "kind", "retrieved_at"], row))
            # republicile unionale sovietice / iugoslave sunt clasificate inconsecvent în Wikidata
            # („federated state”); ca suprafață sunt țări, deci nu pot fi „zonă” la nivel admin1
            if p["kind"] in ("admin1", "admin_other", "region") and SOCIALIST_REPUBLIC.search(p["label"] or ""):
                p["kind"] = "country"
            out[q] = p
    return out


def _place_bindings(batch: list[str], cls_values: str, refresh: bool) -> tuple[list[dict], str]:
    """Rulează PLACE_QUERY; dacă serverul expiră (JSON trunchiat), împarte lotul în două."""
    query = PLACE_QUERY % (" ".join(f"wd:{q}" for q in batch), cls_values)
    try:
        data = sparql(query, cache_key="place:v3:" + ",".join(batch), refresh=refresh)
        return data["data"]["results"]["bindings"], data["retrieved_at"]
    except (ValueError, RuntimeError) as exc:
        if len(batch) == 1:
            log.warning("Loc %s: interogarea a eșuat (%s); îl sar", batch[0], exc)
            return [], http.today()
        half = len(batch) // 2
        log.info("Lot de %d locuri eșuat (%s); îl împart", len(batch), type(exc).__name__)
        b1, r1 = _place_bindings(batch[:half], cls_values, refresh)
        b2, _ = _place_bindings(batch[half:], cls_values, refresh)
        return b1 + b2, r1


def usable(p: dict[str, Any] | None) -> bool:
    """Loc folosibil pe hartă: are coordonate, un tip geografic cunoscut și (sub nivel de țară) o țară.
    Fără țară rămân continente, oceane, regiuni transnaționale („North America”) — prea vagi."""
    if not (p and p.get("kind") and p.get("lat") is not None):
        return False
    return p["kind"] == "country" or bool(p.get("country_qid"))


def precision(p: dict[str, Any]) -> str:
    return PRECISION[p["kind"]]


def countries(refresh: bool = False) -> list[dict[str, Any]]:
    """Toate statele cu cod ISO 3166-1 alpha-2, cu coduri alpha-3/IOC (pentru șabloanele {{flag}} din liste)."""
    data = sparql(COUNTRIES_QUERY, cache_key="countries:v1", refresh=refresh)
    acc: dict[str, dict[str, Any]] = {}
    for b in data["data"]["results"]["bindings"]:
        q = b["c"]["value"].rsplit("/", 1)[-1]
        a = acc.setdefault(q, {"qid": q, "iso2": b["iso2"]["value"], "codes": set()})
        if "label" in b:
            a.setdefault("label", b["label"]["value"])
        for k in ("iso3", "ioc"):
            if k in b:
                a["codes"].add(b[k]["value"].upper())
        if "coord" in b and "coord" not in a:
            pt = _point(b["coord"]["value"])
            if pt:
                a["coord"] = pt
    return list(acc.values())


def run(refresh: bool = False) -> None:
    """Rezolvarea locurilor se face la cerere (cu cache) în timpul build-ului; aici doar o pregătim."""
    from pipeline.build import export
    export.collect(refresh=refresh)
