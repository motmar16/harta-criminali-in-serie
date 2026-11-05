"""Verificare încrucișată: arborele de categorii Wikipedia (engleză) „Serial killers”.

(„Category:Spree killers” nu mai există pe Wikipedia engleză; spree killers vin din Wikidata Q1154323 și Murderpedia.)

Scop: să nu ratăm persoane care au articol, dar nu au ocupația setată în Wikidata și nu apar în liste.
Se parcurg subcategoriile până la o adâncime limitată, sărind ramurile fictive / media / victime.
Rezultat: titlu -> {root, category}; persoanele sunt filtrate apoi la P31 = Q5 în Wikidata.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from pipeline import http
from pipeline.config import RAW
from pipeline.sources.mediawiki import api_url

log = logging.getLogger(__name__)

ROOTS = {"Category:Serial killers": "serial_killer"}
# se rețin doar paginile aflate direct într-o categorie „… serial killers …”, nu în categorii de caz
# („Zodiac Killer” conține și anchetatori, jurnaliști, filme)
KEEP_CAT = re.compile(r"serial killers", re.I)
SKIP = re.compile(r"fiction|film|television|tv |novel|song|album|video game|comics|play\b|musical|opera|"
                  r"victims?\b|investigat|popular culture|works about|books about|documentar|podcast|"
                  r"murders? of|massacres|mass shootings|attacks|cases|hoax|in art|characters", re.I)
MAX_DEPTH = 4


def members(cat: str) -> list[dict[str, Any]]:
    def fetch() -> Any:
        out, cont = [], {}
        while True:
            data = http.request("POST", api_url("en"), data={
                "action": "query", "format": "json", "formatversion": 2, "list": "categorymembers",
                "cmtitle": cat, "cmlimit": "max", "cmprop": "title|ns|type", "cmtype": "page|subcat", **cont}).json()
            out += data.get("query", {}).get("categorymembers", [])
            if "continue" not in data:
                return out
            cont = data["continue"]
    return http.cached_json("wikipedia-categories", cat, fetch)["data"]


def crawl() -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for root, kind in ROOTS.items():
        seen = {root}
        frontier = [(root, 0)]
        while frontier:
            cat, depth = frontier.pop()
            for m in members(cat):
                if m["ns"] == 14:
                    if depth < MAX_DEPTH and m["title"] not in seen and not SKIP.search(m["title"]):
                        seen.add(m["title"])
                        frontier.append((m["title"], depth + 1))
                elif m["ns"] == 0 and KEEP_CAT.search(cat):
                    found.setdefault(m["title"], {"root": kind, "category": cat})
        log.info("%s: %d categorii parcurse, %d pagini până acum", root, len(seen), len(found))
    (RAW / "wikipedia").mkdir(parents=True, exist_ok=True)
    (RAW / "wikipedia" / "category_members.json").write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")
    return found


def load() -> dict[str, dict[str, str]]:
    path = RAW / "wikipedia" / "category_members.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
