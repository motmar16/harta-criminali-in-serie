"""Control de calitate pentru locații + corecturi manuale.

Fișiere (în data/validare/, deschise direct în Excel: UTF-8 cu BOM, separator „;”):
- `locatii_de_verificat.csv` — regenerat la fiecare build: cazurile suspecte, ordonate pe priorități, cu linkuri.
  Coloana `corectura` se completează de mână:
    * unul sau mai multe locuri separate prin „|”: titluri Wikipedia în engleză („Bucharest”,
      „Yonkers, New York”) sau ID-uri Wikidata („Q19660”);
    * „ok” dacă locația actuală e corectă (cazul iese din listă);
  și opțional `nota`.
- `locatii_corectii.csv` — permanent: la fiecare build, corecturile completate în fișierul de mai sus sunt mutate aici,
  ca să nu se piardă când raportul se regenerează. Se poate edita și direct (coloane `id;locuri;nota`).
Exportul aplică corecturile înaintea oricărei surse automate (`active_area` = „manual”).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from pipeline.config import DATA

QA_CSV = DATA / "validare" / "locatii_de_verificat.csv"
FIX_CSV = DATA / "validare" / "locatii_corectii.csv"
WEAK = {"wikipedia-body", "wikipedia-crime-sections", "wikidata-citizenship", "wikipedia-list", "none"}
PRIORITY = {"fara_locatie": 1, "doar_tara": 1, "tara_difera_de_murderpedia": 1, "sursa_slaba": 2,
            "zona_egala_cu_nasterea": 3}
QA_FIELDS = ["prioritate", "id", "nume", "tip", "descriere", "motive", "zona_actuala", "sursa_zonei", "nascut_in",
             "murderpedia_location", "wikipedia", "murderpedia", "radford", "wikidata", "corectura", "nota"]


def _read(path: Path) -> list[dict[str, str]]:
    """CSV salvat de Excel (cu „;” sau „,”, cu sau fără BOM)."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig")
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") >= first.count(",") else ","
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()}
            for r in csv.DictReader(text.splitlines(), delimiter=delim)]


def _write(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_corrections() -> dict[str, list[str]]:
    """id -> locuri (titluri sau QID-uri), sau ["ok"]. Mută întâi corecturile din raportul de verificare."""
    fixes = {r["id"]: r for r in _read(FIX_CSV) if r.get("id") and r.get("locuri")}
    moved = 0
    for r in _read(QA_CSV):
        if r.get("id") and r.get("corectura"):
            fixes[r["id"]] = {"id": r["id"], "locuri": r["corectura"], "nota": r.get("nota", "")}
            moved += 1
    _write(FIX_CSV, ["id", "locuri", "nota"], sorted(fixes.values(), key=lambda r: r["id"]))
    out = {}
    for kid, r in fixes.items():
        vals = [t.strip() for t in r["locuri"].replace(";", "|").split("|") if t.strip()]
        out[kid] = ["ok"] if [v.lower() for v in vals] == ["ok"] else vals
    return out


def report(killers: list[dict[str, Any]], features: list[dict[str, Any]], mp_iso=None) -> dict[str, int]:
    """mp_iso: funcție „Location” Murderpedia -> cod ISO al țării (din murderpedia_merge)."""
    area: dict[str, list[dict[str, Any]]] = {}
    birth: dict[str, dict[str, Any]] = {}
    for f in features:
        p = f["properties"]
        if p["kind"] == "active_area":
            area.setdefault(p["killer_id"], []).append(p)
        elif p["kind"] == "birth":
            birth[p["killer_id"]] = p
    rows, counts = [], {}
    for k in killers:
        basis = k["sources"].get("active_area") or "none"
        if basis == "manual" or k["sources"].get("active_area_verified"):
            continue  # verificat de om
        a = area.get(k["id"], [])
        flags = []
        if not a:
            flags.append("fara_locatie")
        elif a[0]["precision"] == "country":
            flags.append("doar_tara")
        b = birth.get(k["id"])
        if a and b and b["place_id"] == a[0]["place_id"] and basis != "wikipedia-infobox":
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
                "prioritate": min(PRIORITY[f] for f in flags), "id": k["id"], "nume": k["names"]["primary"],
                "tip": ", ".join(k.get("type") or []), "descriere": k.get("description") or "",
                "motive": ", ".join(flags), "zona_actuala": " | ".join(p["place_name"] for p in a),
                "sursa_zonei": basis, "nascut_in": b["place_name"] if b else "",
                "murderpedia_location": mp.get("location") or "",
                "wikipedia": k["links"].get("wikipedia") or "", "murderpedia": k["links"].get("murderpedia") or "",
                "radford": k["links"].get("radford") or "", "wikidata": k["links"].get("wikidata") or "",
                "corectura": "", "nota": "",
            })
    _write(QA_CSV, QA_FIELDS, sorted(rows, key=lambda r: (r["prioritate"], r["motive"], r["nume"])))
    counts["randuri"] = len(rows)
    for p in (1, 2, 3):
        counts[f"prioritate_{p}"] = sum(1 for r in rows if r["prioritate"] == p)
    return counts
