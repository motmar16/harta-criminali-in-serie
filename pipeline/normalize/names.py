"""Nume și slug-uri."""
from __future__ import annotations

import re

from unidecode import unidecode


def slugify(text: str) -> str:
    s = unidecode(text or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80].strip("-")


def primary_name(claims: dict, article_title: str | None = None) -> str:
    """Numele afișat, fără dezambiguări de tip „(serial killer)”."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", _raw_name(claims, article_title)).strip()


def _raw_name(claims: dict, article_title: str | None = None) -> str:
    for key in ("label:en", "label:mul"):
        if claims.get(key):
            return claims[key][0]
    if article_title:
        return re.sub(r"\s*\(.*?\)\s*$", "", article_title)
    for key, vals in claims.items():
        if key.startswith("label:") and vals:
            return vals[0]
    return ""
