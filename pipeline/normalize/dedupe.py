"""Unire Murderpedia <-> persoanele din Wikidata/Wikipedia.

Potrivire: nume normalizat (rapidfuzz token_set_ratio) + an naștere ± 1 + țară. Prag conservator:
- match: scor ≥ 93 și un singur candidat (anul nașterii nu contrazice, țara nu contrazice), sau
  scor 85–93 cu un singur candidat și același an de naștere (± 1);
- ambiguu: mai mulți candidați peste prag, sau scor 85–93 cu an compatibil -> data/validare/dedupe_ambigue.csv,
  unde Marius poate completa coloana `decizie` (QID-ul corect, sau „nou”, sau „diferit”);
- altfel: persoană nouă (doar dacă Murderpedia o clasifică „serial killer”).
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from typing import Any

from rapidfuzz import fuzz
from unidecode import unidecode

from pipeline.config import DATA

AMBIG_CSV = DATA / "validare" / "dedupe_ambigue.csv"
TITLES = {"dr", "sir", "mr", "mrs", "ms", "miss", "jr", "sr", "ii", "iii", "the", "de", "von", "van", "der", "la", "le"}
MATCH, REVIEW = 93, 85


def norm(name: str | None) -> str:
    s = unidecode(name or "").lower()
    s = re.sub(r"\(.*?\)|\".*?\"|'.*?'", " ", s)
    s = re.sub(r"[^a-z ]+", " ", s)
    return " ".join(t for t in s.split() if t not in TITLES and len(t) > 1)


def mp_names(rec: dict[str, Any]) -> list[str]:
    out = []
    if rec.get("title"):
        out.append(rec["title"].split("|")[0])
    if rec.get("index_name"):
        out.append(rec["index_name"])
    return [n for n in (norm(x) for x in out) if n]


def mp_surname(rec: dict[str, Any]) -> str | None:
    """În indexul Murderpedia numele de familie e scris cu majuscule: „Rodney James ALCALA”."""
    caps = [t for t in (rec.get("index_name") or "").split() if len(t) > 1 and t.isupper()]
    return norm(" ".join(caps)).split()[-1] if caps and norm(" ".join(caps)) else None


def year(text: str | None) -> int | None:
    m = re.search(r"(1[5-9]\d\d|20[0-2]\d)", text or "")
    return int(m.group(1)) if m else None


class Matcher:
    def __init__(self, killers: list[dict[str, Any]], extra_names: dict[str, list[str]]):
        self.by_token: dict[str, set[str]] = defaultdict(set)
        self.variants: dict[str, list[str]] = {}
        self.killers = {k["id"]: k for k in killers}
        for k in killers:
            names = {norm(k["names"]["primary"]), *(norm(a) for a in k["names"]["aliases"]),
                     *(norm(n) for n in extra_names.get(k["id"], []))}
            names.discard("")
            self.variants[k["id"]] = sorted(names)
            for n in names:
                for t in n.split():
                    if len(t) > 2:
                        self.by_token[t].add(k["id"])

    def candidates(self, rec: dict[str, Any], mp_iso: str | None) -> list[tuple[int, str, bool]]:
        names = mp_names(rec)
        toks = {t for n in names for t in n.split() if len(t) > 2}
        sur = mp_surname(rec)
        pool = set()
        for t in ([sur] if sur else []) or list(toks):
            pool |= self.by_token.get(t, set())
        if not pool:
            for t in toks:
                pool |= self.by_token.get(t, set())
        by = year(rec.get("date_of_birth"))
        out = []
        for kid in pool:
            k = self.killers[kid]
            score = max((fuzz.token_set_ratio(a, b) for a in names for b in self.variants[kid]), default=0)
            # token_set_ratio dă 100 și când un nume e inclus în altul („John Smith” ⊂ „John Henry Smith”);
            # cerem și o potrivire de ordine rezonabilă
            score = min(score, max((fuzz.token_sort_ratio(a, b) for a in names for b in self.variants[kid]),
                                   default=0) + 15)
            if score < REVIEW:
                continue
            kby = year((k.get("birth") or {}).get("date"))
            if by and kby and abs(by - kby) > 1:
                continue
            year_ok = bool(by and kby)
            country_ok = not mp_iso or not k["countries"] or mp_iso in k["countries"]
            if not country_ok and not year_ok:
                continue
            out.append((int(score), kid, year_ok))
        return sorted(out, reverse=True)


def decide(cands: list[tuple[int, str, bool]]) -> tuple[str, str | None]:
    """-> ("match", qid) | ("ambiguous", None) | ("none", None)."""
    strong = [c for c in cands if c[0] >= MATCH]
    if len(strong) == 1:
        return "match", strong[0][1]
    if len(strong) > 1:
        dated = [c for c in strong if c[2]]
        if len(dated) == 1:
            return "match", dated[0][1]
        return "ambiguous", None
    dated = [c for c in cands if c[2]]  # scor 85–93, dar anul nașterii se potrivește
    if len(dated) == 1 and len(cands) == 1:
        return "match", dated[0][1]
    if dated:
        return "ambiguous", None
    return "none", None


def load_manual_decisions() -> dict[str, str]:
    """Deciziile completate manual în CSV (coloana `decizie`), păstrate între rulări."""
    if not AMBIG_CSV.exists():
        return {}
    with AMBIG_CSV.open(encoding="utf-8", newline="") as f:
        return {r["murderpedia_url"]: r["decizie"].strip() for r in csv.DictReader(f) if r.get("decizie", "").strip()}


def write_ambiguous(rows: list[dict[str, Any]], decisions: dict[str, str]) -> None:
    AMBIG_CSV.parent.mkdir(parents=True, exist_ok=True)
    with AMBIG_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["murderpedia_url", "murderpedia_nume", "nascut", "locatie", "candidati", "decizie"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "decizie": decisions.get(r["murderpedia_url"], "")})
