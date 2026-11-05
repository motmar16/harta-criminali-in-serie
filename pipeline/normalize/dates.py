"""Date: valori de timp Wikidata și ani din câmpurile infobox."""
from __future__ import annotations

import re
from typing import Any

PRECISION = {11: "day", 10: "month", 9: "year", 8: "decade", 7: "century"}


def wikidata_time(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """{"time": "1936-10-16T00:00:00Z", "precision": 11} -> {"date": "1936-10-16", "precision": "day"}."""
    if not value:
        return None
    m = re.match(r"^([-+]?)(\d+)-(\d\d)-(\d\d)T", value["time"])
    if not m:
        return None
    sign, y, mo, d = m.groups()
    prec = PRECISION.get(value.get("precision", 9), "year")
    year = f"{'-' if sign == '-' else ''}{int(y):04d}"
    if prec == "day":
        date = f"{year}-{mo}-{d}"
    elif prec == "month":
        date = f"{year}-{mo}"
    else:
        date = year
    return {"date": date, "precision": prec}


def years(text: str | None) -> list[int]:
    """Anii (3–4 cifre, cu „BC” negativ) dintr-un text de infobox ca „May 1971”, „c. 1566”, „144–116 BC”."""
    if not text:
        return []
    out = []
    bc = bool(re.search(r"\bBC\b|\bBCE\b", text))
    for m in re.finditer(r"(?<!\d)(\d{3,4})(?!\d)", text):
        y = int(m.group(1))
        if 100 <= y <= 2100:
            out.append(-y if bc else y)
    return out


def active_period(begin: str | None, end: str | None, years_active: str | None = None) -> dict[str, Any] | None:
    # „BC” apare de obicei doar la final („144 … 116 BC”), deci se aplică ambelor capete
    ys = years(f"{begin or ''} ; {end or ''}") if (begin or end) else []
    if not ys:
        ys = years(years_active)
    if not ys:
        return None
    return {"start": str(min(ys)), "end": str(max(ys))}
