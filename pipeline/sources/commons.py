"""Wikimedia Commons: imaginile P18 din Wikidata, cu licență și autor verificate din metadatele fișierului.

Se acceptă doar licențe libere recunoscute (domeniu public, CC0, CC BY, CC BY-SA, FAL, OGL, GFDL). Altfel: fără imagine.
Fișierele al căror nume sugerează victime sau locul crimei sunt excluse.
"""
from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Iterable
from urllib.parse import unquote

from pipeline import http
from pipeline.config import RAW

log = logging.getLogger(__name__)

API = "https://commons.wikimedia.org/w/api.php"
FREE = re.compile(r"^(public domain|pd\b|pd-|cc0|cc[ -]by(?:[ -]sa)?(?:[ -]\d(?:\.\d)?)?|fal\b|ogl\b|gfdl)", re.I)
# fișiere care, după nume, pot arăta victime sau locul crimei (principiul 6: fără fotografii cu victime)
NOT_PORTRAIT = re.compile(r"victim|body|bodies|corpse|crime[ _-]?scene|grave|murder[ _-]?site|skull", re.I)


def file_title(value: str) -> str:
    """„http://commons.wikimedia.org/wiki/Special:FilePath/X%20Y.jpg” -> „File:X Y.jpg”."""
    name = unquote(value.rsplit("/", 1)[-1]).replace("_", " ")
    return name if name.startswith("File:") else f"File:{name}"


def _clean(s: str | None) -> str | None:
    if not s:
        return None
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:200] or None


def _strip(url: str | None) -> str | None:
    return url.split("?", 1)[0] if url else url


def _batches(items: list[str], n: int = 50) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


def image_info(files: list[str]) -> dict[str, dict[str, Any] | None]:
    """Fișier Commons -> {url, thumb, license, license_url, credit, page} sau None dacă licența nu e liberă."""
    files = sorted(set(files))
    out: dict[str, dict[str, Any] | None] = {}
    for batch in _batches(files):
        key = "imageinfo:v1:" + "|".join(batch)

        def fetch(batch=batch) -> Any:
            return http.request("POST", API, data={
                "action": "query", "format": "json", "formatversion": 2, "titles": "|".join(batch),
                "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 480,
                "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|Credit|UsageTerms|AttributionRequired",
            }).json()

        data = http.cached_json("commons", key, fetch)["data"]
        norm = {n["to"]: n["from"] for n in data.get("query", {}).get("normalized", [])}
        for p in data.get("query", {}).get("pages", []):
            name = norm.get(p["title"], p["title"])
            ii = (p.get("imageinfo") or [None])[0]
            if not ii:
                out[name] = None
                continue
            md = {k: (v or {}).get("value") for k, v in (ii.get("extmetadata") or {}).items()}
            lic = _clean(md.get("LicenseShortName")) or ""
            if NOT_PORTRAIT.search(name):
                out[name] = None
                continue
            if not FREE.match(lic):
                log.info("Imagine respinsă (licență „%s”): %s", lic, name)
                out[name] = None
                continue
            out[name] = {
                "url": _strip(ii.get("url")), "thumb": _strip(ii.get("thumburl") or ii.get("url")),
                "page": ii.get("descriptionurl"), "license": lic, "license_url": md.get("LicenseUrl"),
                "credit": _clean(md.get("Artist")) or _clean(md.get("Credit")) or "Wikimedia Commons",
            }
    return out


def run(people: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """QID -> imagine verificată; rezultatul se salvează în data/raw/commons/images.json."""
    wanted = {q: file_title(p["claims"]["P18"][0]) for q, p in people.items() if p["claims"].get("P18")}
    info = image_info(list(wanted.values()))
    res = {q: info.get(f) for q, f in wanted.items() if info.get(f)}
    (RAW / "commons").mkdir(parents=True, exist_ok=True)
    (RAW / "commons" / "images.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    log.info("Commons: %d imagini cu licență liberă din %d cerute", len(res), len(wanted))
    return res
