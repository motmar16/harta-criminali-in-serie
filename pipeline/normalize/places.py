"""Locuri: jitter determinist pentru puncte imprecise și număr de victime din text."""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any

# raza maximă a decalajului, în grade, după precizie
JITTER_DEG = {"address": 0.0, "city": 0.012, "county": 0.08, "admin1": 0.35, "country": 1.2}


def jitter(lat: float, lon: float, key: str, precision: str) -> tuple[float, float]:
    """Decalaj determinist (același pentru aceeași cheie), ca punctele să nu se suprapună pe centroid."""
    r_max = JITTER_DEG.get(precision, 0.0)
    if r_max == 0:
        return lat, lon
    h = hashlib.sha1(key.encode("utf-8")).digest()
    angle = int.from_bytes(h[:4], "big") / 2**32 * 2 * math.pi
    r = math.sqrt(int.from_bytes(h[4:8], "big") / 2**32) * r_max
    dlat = r * math.sin(angle)
    dlon = r * math.cos(angle) / max(math.cos(math.radians(lat)), 0.2)
    return round(lat + dlat, 5), round(((lon + dlon + 180) % 360) - 180, 5)


def parse_victims(text: str | None, wikidata_counts: list[str] | None = None) -> dict[str, Any] | None:
    """„22–29”, „10+”, „36 confirmed, 43 confessed, 55+ estimated” -> {proven, possible, note}.

    Primul număr e considerat „proven”, cel mai mare (dacă e mai mare) „possible”; originalul rămâne în note.
    """
    wd = []
    for v in wikidata_counts or []:
        try:
            wd.append(int(float(v)))
        except ValueError:
            pass
    nums = []
    if text:
        clean = re.sub(r"\b(1[0-9]{3}|20[0-9]{2})\b", " ", text)  # fără ani
        nums = [int(n) for n in re.findall(r"(?<![\d.])(\d{1,4})(?![\d.])", clean.replace(",", " "))]
        nums = [n for n in nums if n <= 1000]
    if not wd and not nums:
        return None
    if wd:
        proven = max(wd)
        possible = max(nums) if nums and max(nums) > proven else None
        source = "wikidata"
    else:
        proven = nums[0]
        possible = max(nums) if max(nums) > proven else None
        source = "wikipedia-infobox"
    return {"proven": proven, "possible": possible, "note": (text or "")[:200] or None, "source": source}
