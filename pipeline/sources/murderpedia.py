"""Murderpedia: indexuri (bărbați/femei A–Z) + profiluri; DOAR câmpurile structurate (fapte).

Principii (PLAN secțiunea 3):
- se extrag numai câmpurile etichetate: Classification, Characteristics, Number of victims, Date of murder,
  Date of arrest, Date of birth, Victim profile, Method of murder, Location, Status + nume + URL;
  narațiunea, articolele de presă și fotografiile NU se preiau (doar un indicator că există galerie foto);
- HTML-ul brut stă în data/raw/murderpedia/ (gitignored); paginile sunt cp1252;
- 1 cerere/secundă, cache strict: o rerulare nu mai atinge rețeaua pentru paginile deja descărcate.
"""
from __future__ import annotations

import html
import json
import logging
import re
import string
import time
from typing import Any
from urllib.parse import urljoin

from pipeline import http
from pipeline.config import RAW

log = logging.getLogger(__name__)

BASE = "https://murderpedia.org/"
INDEXES = [f"{BASE}{sex}.{L}/index.{L}.htm" for sex in ("male", "female") for L in string.ascii_uppercase]
FIELDS = {
    "classification": r"Classification",
    "characteristics": r"Characteristics",
    "victims": r"Number of victims",
    "date_of_murder": r"Dates? of (?:the )?murders?",
    "date_of_arrest": r"Dates? of arrest",
    "date_of_birth": r"Dates? of birth",
    "victim_profile": r"Victims? profiles?",
    "method": r"Methods? of (?:the )?murders?",
    "location": r"Locations?",
    "status": r"Status",
}
LABEL_RE = re.compile(r"(" + "|".join(f"(?P<{k}>{v})" for k, v in FIELDS.items()) + r")\s*:", re.I)
OUT = RAW / "murderpedia"


def fetch_html(url: str) -> str:
    """HTML decodat cp1252, din cache (data/raw/murderpedia/) sau descărcat o singură dată."""
    path = http.cache_path("murderpedia", url, ".htm")
    if path.exists():
        return path.read_text(encoding="utf-8")
    resp = http.request("GET", url)
    text = resp.content.decode("cp1252", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def _text(fragment: str) -> str:
    fragment = re.sub(r"(?is)<script.*?</script>", " ", fragment)
    # tagurile de bloc separă cuvinte; cele inline (b, font, span…) pot fi în mijlocul unui cuvânt („Canad<b>a”)
    fragment = re.sub(r"(?i)<(?:br|/?p|/?td|/?tr|/?div|/?li|/?table)[^>]*>", " ", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(fragment)).strip()


def parse_index(page_url: str, page: str) -> list[dict[str, Any]]:
    """Rândurile tabelului de index: URL profil, nume, dată, victime, loc (text scurt)."""
    sex = "female" if "/female." in page_url else "male"
    out = []
    for row in re.findall(r"(?is)<tr\b.*?</tr>", page):
        hrefs = [h for h in re.findall(r'href="([^"#]+\.htm)"', row, flags=re.I)
                 if not h.startswith(("http", "mailto", "../")) and "index" not in h]
        if not hrefs:
            continue
        cells = [_text(c) for c in re.findall(r"(?is)<td\b.*?</td>", row)]
        cells = [c for c in cells if c]
        if len(cells) < 2:
            continue
        out.append({"url": urljoin(page_url, hrefs[0]), "sex": sex, "index_name": cells[0],
                    "index_date": cells[1] if len(cells) > 1 else None,
                    "index_victims": cells[2] if len(cells) > 2 else None,
                    "index_location": cells[3] if len(cells) > 3 else None})
    return out


def parse_profile(url: str, page: str) -> dict[str, Any]:
    """Câmpurile etichetate din antetul profilului. Valoarea = textul până la următoarea etichetă."""
    title = _text((re.search(r"(?is)<title>(.*?)</title>", page) or [None, ""])[1])
    rec: dict[str, Any] = {"url": url, "title": title}
    # întâi per celulă: fiecare câmp etichetat are, de regulă, celula lui de tabel
    for cell in re.findall(r"(?is)<td\b[^>]*>(.*?)</td>", page):
        ct = _text(cell)
        m = LABEL_RE.match(ct)
        if m and len(ct) < 600:
            key = next(k for k in FIELDS if m.group(k))
            rec.setdefault(key, ct[m.end():].strip(" .;,-:")[:300] or None)
    if sum(1 for k in FIELDS if k in rec) >= 3:
        rec["has_photos"] = bool(re.search(r'src="[^"]*images/', page, flags=re.I))
        return rec
    # rezervă: pe textul întreg, până la următoarea etichetă
    text = _text(page)
    matches = list(LABEL_RE.finditer(text))
    first_seen: set[str] = set()
    for i, m in enumerate(matches):
        key = next(k for k in FIELDS if m.group(k))
        if key in first_seen:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else m.end() + 300
        value = text[m.end():min(end, m.end() + 300)].strip(" .;,-")
        if key == "status":
            # după Status începe narațiunea; păstrăm doar prima propoziție
            value = re.split(r"(?<=[a-z0-9\)])\.\s", value, maxsplit=1)[0][:250]
        first_seen.add(key)
        rec[key] = value or None
    rec["has_photos"] = bool(re.search(r'src="[^"]*images/', page, flags=re.I))
    return rec


def mp_type(rec: dict[str, Any]) -> str | None:
    """Tipul după eticheta Murderpedia: „Serial killer” -> serial_killer, „Spree killer” -> spree_killer."""
    c = (rec.get("classification") or "").lower()
    if "serial" in c:
        return "serial_killer"
    if "spree" in c:
        return "spree_killer"
    return None


def is_serial(rec: dict[str, Any]) -> bool:
    return mp_type(rec) == "serial_killer"


def run(refresh: bool = False, limit: int | None = None) -> None:
    t0 = time.time()
    rows: dict[str, dict[str, Any]] = {}
    for idx in INDEXES:
        try:
            page = fetch_html(idx)
        except Exception as exc:  # noqa: BLE001 - un index lipsă nu oprește restul
            log.warning("Index %s: %s", idx, exc)
            continue
        for r in parse_index(idx, page):
            rows.setdefault(r["url"], r)
    log.info("Murderpedia: %d profiluri în indexuri", len(rows))
    urls = list(rows)[:limit] if limit else list(rows)
    profiles = []
    failed = 0
    for n, url in enumerate(urls, 1):
        try:
            page = fetch_html(url)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log.warning("Profil %s: %s", url, exc)
            continue
        rec = parse_profile(url, page)
        rec.update({k: v for k, v in rows[url].items() if k != "url"})
        profiles.append(rec)
        if n % 250 == 0:
            log.info("  … %d/%d profiluri (%d serial)", n, len(urls), sum(map(is_serial, profiles)))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "profiles.json").write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
    log.info("Murderpedia gata: %d profiluri parsate, %d eșuate, %d clasificate serial, în %.0f min",
             len(profiles), failed, sum(map(is_serial, profiles)), (time.time() - t0) / 60)


def load_profiles() -> list[dict[str, Any]]:
    return json.loads((OUT / "profiles.json").read_text(encoding="utf-8"))
