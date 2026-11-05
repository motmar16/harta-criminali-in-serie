"""Control de calitate pentru locații + corecturi manuale.

- `data/validare/locatii_de_verificat.csv`: cazurile suspecte, cu motivul (doar țară, zona = locul nașterii,
  sursă slabă, țară diferită de Murderpedia). Generat la fiecare build.
- `data/validare/locatii_corectii.csv` (scris de om): coloanele `id`, `locuri` (titluri Wikipedia engleză separate
  prin „;”, ex. „Bucharest” sau „Yonkers, New York; Albany, New York”), `nota`. Exportul le aplică înaintea
  oricărei surse automate (`active_area` = „manual”).
"""
from __future__ import annotations

import csv
from typing import Any

from pipeline.config import DATA

QA_CSV = DATA / "validare" / "locatii_de_verificat.csv"
FIX_CSV = DATA / "validare" / "locatii_corectii.csv"
WEAK = {"wikipedia-body", "wikipedia-crime-sections", "wikidata-citizenship", "wikipedia-list", "none"}


def load_corrections() -> dict[str, list[str]]:
    if not FIX_CSV.exists():
        FIX_CSV.parent.mkdir(parents=True, exist_ok=True)
        with FIX_CSV.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["id", "locuri", "nota"])
        return {}
    with FIX_CSV.open(encoding="utf-8", newline="") as f:
        return {r["id"].strip(): [t.strip() for t in r["locuri"].split(";") if t.strip()]
                for r in csv.DictReader(f) if r.get("id") and r.get("locuri")}


def report(killers: list[dict[str, Any]], features: list[dict[str, Any]], mp_iso=None) -> dict[str, int]:
    """mp_iso: funcție „Location” Murderpedia -> cod ISO al țării (din murderpedia_merge)."""
    area: dict[str, list[dict[str, Any]]] = {}
    birth: dict[str, str] = {}
    for f in features:
        p = f["properties"]
        if p["kind"] == "active_area":
            area.setdefault(p["killer_id"], []).append(p)
        elif p["kind"] == "birth":
            birth[p["killer_id"]] = p["place_id"]
    rows, counts = [], {}
    for k in killers:
        a = area.get(k["id"], [])
        basis = k["sources"].get("active_area") or "none"
        flags = []
        if not a:
            flags.append("fara_locatie")
        elif a[0]["precision"] == "country":
            flags.append("doar_tara")
        if a and birth.get(k["id"]) == a[0]["place_id"] and basis not in ("wikipedia-infobox", "manual"):
            flags.append("zona_egala_cu_nasterea")
        if basis in WEAK and a and a[0]["precision"] != "country":
            flags.append("sursa_slaba")
        mp = k.get("murderpedia") or {}
        if mp_iso and mp.get("location") and a and basis != "murderpedia":
            iso = mp_iso(mp["location"])
            if iso and k["countries"] and iso not in k["countries"]:
                flags.append("tara_difera_de_murderpedia")
        for fl in flags:
            counts[fl] = counts.get(fl, 0) + 1
        if flags:
            rows.append({
                "id": k["id"], "nume": k["names"]["primary"], "motive": ",".join(flags), "sursa": basis,
                "zona": "; ".join(p["place_name"] for p in a), "murderpedia_location": mp.get("location") or "",
                "wikipedia": k["links"].get("wikipedia") or "", "murderpedia": k["links"].get("murderpedia") or "",
            })
    QA_CSV.parent.mkdir(parents=True, exist_ok=True)
    with QA_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "nume", "motive", "sursa", "zona", "murderpedia_location",
                                          "wikipedia", "murderpedia"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["motive"], r["nume"])))
    counts["randuri"] = len(rows)
    return counts
