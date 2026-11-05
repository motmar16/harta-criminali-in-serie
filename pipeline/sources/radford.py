"""Radford University: „Serial Killer Timelines” (biografii-cronologie scrise de studenți, PDF per criminal).

Pagina: https://maamodt.asp.radford.edu/Psyc%20405/serial_killer_timelines.htm
Se preiau DOAR fapte: linkul PDF (afișat ca sursă pe fișă) și locurile pomenite în rândurile cronologiei care
vorbesc despre crime. Textul PDF-urilor nu intră în repo; PDF-urile stau în data/raw/radford/ (gitignored).
"""
from __future__ import annotations

import json
import logging
import re
from io import BytesIO
from typing import Any
from urllib.parse import unquote, urljoin

from pypdf import PdfReader

from pipeline import http
from pipeline.config import RAW

log = logging.getLogger(__name__)

INDEX = "https://maamodt.asp.radford.edu/Psyc%20405/serial_killer_timelines.htm"
OUT = RAW / "radford"

US_STATES = ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
             "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
             "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana",
             "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
             "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
             "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
             "Wisconsin", "Wyoming"]
STATE_ABBR = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
              "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
              "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
              "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
              "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
              "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
              "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
              "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
              "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
              "WI": "Wisconsin", "WY": "Wyoming"}
CRIME = re.compile(r"murder|kill|victim|body|bodies|strangl|stabb|shot|abduct|kidnap|rape|disappear|remains", re.I)
BIRTH = re.compile(r"\bborn\b|birth|moves? to|moved to|family|grade|school|graduat|married|enlist|divorc", re.I)
_STATE_RE = "|".join(sorted(US_STATES, key=len, reverse=True))
CITY_STATE = re.compile(r"\b((?:[A-Z][a-zA-Z.'-]+ ){0,3}[A-Z][a-zA-Z.'-]+),\s*(" + _STATE_RE + r"|[A-Z]{2})\b")


IN_PLACE = re.compile(r"\b(?:in|near|at|outside|from) ((?:[A-Z][a-zA-Z.'-]+ ){0,2}[A-Z][a-zA-Z.'-]{2,})")
NOT_PLACE = {"January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December", "The", "His", "Her", "He", "She", "They", "A", "An", "Court", "Prison",
             "State", "County", "Police", "Death", "Life", "Room", "Apartment", "House", "Home", "Church", "School"}


def index() -> list[dict[str, str]]:
    path = http.cache_path("radford", INDEX, ".htm")
    if path.exists():
        page = path.read_text(encoding="utf-8")
    else:
        resp = http.request("GET", INDEX)
        page = resp.content.decode(resp.encoding or "cp1252", errors="replace")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page, encoding="utf-8")
    out = []
    for href in dict.fromkeys(re.findall(r'href="([^"]+\.pdf)"', page, flags=re.I)):
        url = urljoin(INDEX, href)
        stem = unquote(href.rsplit("/", 1)[-1])[:-4]
        # „Alcala. Rodney _2012_”, „Barfield, Velma - 2005, Fall” -> „Velma Barfield”
        stem = re.sub(r"\s*[-_(].*$", "", stem).replace(".", ",")
        last, _, first = stem.partition(",")
        out.append({"url": url, "name": f"{first.strip()} {last.strip()}".strip(), "last": last.strip()})
    return out


def pdf_text(url: str) -> str:
    path = http.cache_path("radford", url, ".pdf")
    if not path.exists():
        data = http.request("GET", url).content
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    try:
        reader = PdfReader(BytesIO(path.read_bytes()))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as exc:  # noqa: BLE001 - un PDF stricat nu oprește restul
        log.warning("PDF ilizibil %s: %s", url, exc)
        return ""


def crime_places(text: str) -> list[str]:
    """Titluri candidate „Oraș, Stat” din rândurile cronologiei despre crime (nu despre copilărie/familie)."""
    out: list[str] = []
    # PDF-ul rupe rândurile tabelului pe mai multe linii; un rând nou începe cu o dată („08/10/1933”, „1951”)
    rows = re.split(r"\n(?=\s*(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{4}\b|(?:Early|Late|Mid)[- ]\d{4}|N/A|No\s))", text)
    for row in rows:
        row = re.sub(r"\s*\n\s*", " ", row)
        for line in re.split(r"(?<=[.;])\s+", row):
            if CRIME.search(line) and not BIRTH.search(line):
                out += _line_places(line)
    return out


def _line_places(line: str) -> list[str]:
    out: list[str] = []
    for city, state in CITY_STATE.findall(line):
        state = STATE_ABBR.get(state, state)
        if state in US_STATES:
            out.append(f"{city.strip()}, {state}")
    # „killed … in Rostov”, „body found near Green River”: candidați verificați apoi după țară
    for name in IN_PLACE.findall(line):
        if name.split()[0] not in NOT_PLACE:
            out.append(name)
    # antetul PDF-ului („Department of Psychology, Radford University, Radford, VA”) nu e un loc al crimelor
    return [p for p in out if "radford" not in p.lower()]


def run() -> list[dict[str, Any]]:
    recs = []
    for r in index():
        text = pdf_text(r["url"])
        recs.append({**r, "places": crime_places(text), "chars": len(text)})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "timelines.json").write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    log.info("Radford: %d cronologii, %d cu locuri extrase", len(recs), sum(1 for r in recs if r["places"]))
    return recs


def load() -> list[dict[str, Any]]:
    path = OUT / "timelines.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
