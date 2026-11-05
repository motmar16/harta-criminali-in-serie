"""Acces MediaWiki API (orice Wikipedia), pe loturi de 50 de titluri, cu cache per titlu în data/raw/wikipedia/."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable

from pipeline import http

log = logging.getLogger(__name__)

BATCH = 50


def api_url(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/w/api.php"


def _batches(items: list[str], n: int = BATCH) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


def query_all(lang: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Execută action=query cu continuare; întoarce paginile combinate + normalizări/redirecturi."""
    base = {"action": "query", "format": "json", "formatversion": 2, "redirects": 1, **params}
    pages: dict[int | str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    cont: dict[str, Any] = {}
    while True:
        data = http.request("POST", api_url(lang), data={**base, **cont}).json()
        q = data.get("query", {})
        for n in q.get("normalized", []) + q.get("redirects", []):
            aliases[n["from"]] = n["to"]
        for p in q.get("pages", []):
            key = p.get("pageid") or p["title"]
            if key in pages:
                for k, v in p.items():
                    if isinstance(v, list):
                        pages[key].setdefault(k, []).extend(v)
                    else:
                        pages[key].setdefault(k, v)
            else:
                pages[key] = p
        if "continue" not in data:
            break
        cont = data["continue"]
    out = list(pages.values())
    # atașăm fiecărei pagini titlurile cerute care au ajuns la ea
    by_title = {p["title"]: p for p in out}
    for src in list(aliases):
        dst = src
        seen = set()
        while dst in aliases and dst not in seen:
            seen.add(dst)
            dst = aliases[dst]
        if dst in by_title:
            by_title[dst].setdefault("requested_as", []).append(src)
    return out


def _page_cache(lang: str, title: str) -> Path:
    return http.cache_path(f"wikipedia/{lang}", title)


def fetch_pages(lang: str, titles: list[str], refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Wikitext + revid + QID pentru fiecare titlu. Cache per titlu (inclusiv lipsă)."""
    result: dict[str, dict[str, Any]] = {}
    missing = []
    for t in dict.fromkeys(titles):
        path = _page_cache(lang, t)
        if path.exists() and not refresh:
            result[t] = json.loads(path.read_text(encoding="utf-8"))
        else:
            missing.append(t)
    if missing:
        log.info("%s.wikipedia: descarc %d articole (%d din cache)", lang, len(missing), len(result))
    for batch in _batches(missing):
        pages = query_all(lang, {"prop": "revisions|pageprops", "rvprop": "content|ids|timestamp",
                                 "rvslots": "main", "ppprop": "wikibase_item", "titles": "|".join(batch)})
        found: dict[str, dict[str, Any]] = {}
        for p in pages:
            rev = (p.get("revisions") or [{}])[0]
            rec = {
                "lang": lang, "title": p["title"], "missing": bool(p.get("missing")),
                "pageid": p.get("pageid"), "revid": rev.get("revid"), "timestamp": rev.get("timestamp"),
                "qid": (p.get("pageprops") or {}).get("wikibase_item"),
                "wikitext": ((rev.get("slots") or {}).get("main") or {}).get("content"),
                "retrieved_at": http.today(),
            }
            for name in [p["title"], *p.get("requested_as", [])]:
                found[name] = rec
        for t in batch:
            rec = found.get(t) or {"lang": lang, "title": t, "missing": True, "retrieved_at": http.today()}
            path = _page_cache(lang, t)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            result[t] = rec
    return result


def resolve_qids(lang: str, titles: list[str]) -> dict[str, str | None]:
    """Titlu -> QID Wikidata (urmează redirecturile). Fără cache aici; vezi geocode.wikidata_places."""
    out: dict[str, str | None] = {}
    for batch in _batches(titles):
        pages = query_all(lang, {"prop": "pageprops", "ppprop": "wikibase_item", "titles": "|".join(batch)})
        for p in pages:
            qid = (p.get("pageprops") or {}).get("wikibase_item")
            for name in [p["title"], *p.get("requested_as", [])]:
                out[name] = qid
        for t in batch:
            out.setdefault(t, None)
    return out
