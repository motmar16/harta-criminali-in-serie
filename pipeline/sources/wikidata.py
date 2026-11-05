"""Wikidata: lista criminalilor în serie (Q484188) și proprietățile lor, prin SPARQL.

Pașii:
1. `fetch_qids()` — toate item-urile umane cu P106 = Q484188 sau P31/P279* = Q484188.
2. `fetch_details(qids)` — proprietăți pe loturi (VALUES), câte un rând per (persoană, proprietate, valoare).
Rezultatul agregat se scrie în data/raw/wikidata/people.json (gitignored) și e citit de build.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Any, Iterable

from pipeline import http
from pipeline.config import RAW

log = logging.getLogger(__name__)

ENDPOINT = "https://query.wikidata.org/sparql"
SERIAL_KILLER = "Q484188"
BATCH = 200

SPREE_KILLER = "Q1154323"
OCCUPATIONS = {SERIAL_KILLER: "serial_killer", SPREE_KILLER: "spree_killer"}

QIDS_QUERY = """
SELECT DISTINCT ?p WHERE {
  { ?p wdt:P106 wd:%(o)s } UNION { ?p wdt:P31/wdt:P279* wd:%(o)s }
  ?p wdt:P31 wd:Q5 .
}
"""

# Un rând per (persoană, proprietate, valoare); evită produsul cartezian al OPTIONAL-urilor din Anexa A.
DETAILS_QUERY = """
SELECT ?p ?prop ?v ?prec WHERE {
  VALUES ?p { %s }
  {
    ?p wdt:P21|wdt:P19|wdt:P20|wdt:P27|wdt:P1196|wdt:P18|wdt:P1399|wdt:P551|wdt:P106|wdt:P31|wdt:P1345 ?v .
    ?p ?direct ?v . ?prop_ wikibase:directClaim ?direct .
    FILTER(?prop_ IN (wd:P21, wd:P19, wd:P20, wd:P27, wd:P1196, wd:P18, wd:P1399, wd:P551, wd:P106, wd:P31, wd:P1345))
    BIND(STRAFTER(STR(?prop_), "entity/") AS ?prop)
  }
  UNION { ?p p:P569 ?st . ?st a wikibase:BestRank ; psv:P569 ?n . ?n wikibase:timeValue ?v ; wikibase:timePrecision ?prec . BIND("P569" AS ?prop) }
  UNION { ?p p:P570 ?st . ?st a wikibase:BestRank ; psv:P570 ?n . ?n wikibase:timeValue ?v ; wikibase:timePrecision ?prec . BIND("P570" AS ?prop) }
  UNION { ?p rdfs:label ?v . FILTER(LANG(?v) IN ("en", "mul", "de", "fr", "es", "it", "pt", "ru", "pl", "nl")) BIND(CONCAT("label:", LANG(?v)) AS ?prop) }
  UNION { ?p schema:description ?v . FILTER(LANG(?v) = "en") BIND("description" AS ?prop) }
  UNION { ?p skos:altLabel ?v . FILTER(LANG(?v) = "en") BIND("alias" AS ?prop) }
  UNION { ?a schema:about ?p ; schema:isPartOf ?wiki ; schema:name ?title .
          FILTER(CONTAINS(STR(?wiki), ".wikipedia.org"))
          BIND(CONCAT(STR(?wiki), "|", STR(?title)) AS ?v) BIND("sitelink" AS ?prop) }
}
"""


def sparql(query: str, *, cache_key: str, refresh: bool = False) -> dict[str, Any]:
    def fetch() -> Any:
        resp = http.request("POST", ENDPOINT, data={"query": query, "format": "json"})
        return resp.json()
    return http.cached_json("wikidata", cache_key, fetch, refresh=refresh)


def _qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def fetch_qids(refresh: bool = False) -> dict[str, set[str]]:
    """QID -> tipuri („serial_killer”, „spree_killer”) după ocupația/clasa din Wikidata.
    O interogare per ocupație (combinate, expiră pe server)."""
    out: dict[str, set[str]] = {}
    for occ, kind in OCCUPATIONS.items():
        res = sparql(QIDS_QUERY % {"o": occ}, cache_key=f"qids:v3:{occ}", refresh=refresh)
        for b in res["data"]["results"]["bindings"]:
            out.setdefault(_qid(b["p"]["value"]), set()).add(kind)
    log.info("Wikidata: %d item-uri umane (%d serial, %d spree)", len(out),
             sum("serial_killer" in t for t in out.values()), sum("spree_killer" in t for t in out.values()))
    return out


def _batches(items: list[str], n: int) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


def fetch_details(qids: list[str], refresh: bool = False) -> dict[str, dict[str, Any]]:
    people: dict[str, dict[str, Any]] = {}
    for i, batch in enumerate(_batches(qids, BATCH)):
        values = " ".join(f"wd:{q}" for q in batch)
        res = sparql(DETAILS_QUERY % values, cache_key=f"details:v1:{','.join(batch)}", refresh=refresh)
        retrieved = res["retrieved_at"]
        rows: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for b in res["data"]["results"]["bindings"]:
            q = _qid(b["p"]["value"])
            prop = b["prop"]["value"]
            v = b["v"]["value"]
            if b["v"].get("type") == "uri" and "/entity/" in v:
                v = _qid(v)
            if prop in ("P569", "P570"):
                v = {"time": v, "precision": int(b["prec"]["value"])}
            if v not in rows[q][prop]:
                rows[q][prop].append(v)
        for q in batch:
            people[q] = {"id": q, "retrieved_at": retrieved, "claims": {k: v for k, v in rows.get(q, {}).items()}}
        log.info("Wikidata detalii: lot %d (%d persoane)", i + 1, len(batch))
    return people


def load_people() -> dict[str, dict[str, Any]]:
    path = RAW / "wikidata" / "people.json"
    return json.loads(path.read_text(encoding="utf-8"))


def save_people(people: dict[str, dict[str, Any]]) -> None:
    path = RAW / "wikidata" / "people.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(people, ensure_ascii=False), encoding="utf-8")


def run(refresh: bool = False) -> None:
    t0 = time.time()
    types = fetch_qids(refresh=refresh)
    qids = sorted(types, key=lambda q: int(q[1:]))
    people = fetch_details(qids, refresh=refresh)
    for q, p in people.items():
        p["origin"] = "wikidata-sparql"
        p["types"] = sorted(types[q])
    save_people(people)
    log.info("Wikidata gata: %d persoane în %.0fs", len(people), time.time() - t0)
