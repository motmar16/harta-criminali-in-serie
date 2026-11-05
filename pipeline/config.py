"""Căi și setări comune pentru pipeline."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"  # cache brut, gitignored (principiul 5)
SITE_DATA = ROOT / "site" / "public" / "data"
GEOCODE_CACHE = ROOT / "pipeline" / "geocode" / "cache.sqlite"

# User-Agent explicit (principiul 3). Contactul se setează prin HARTA_CONTACT
# (email sau URL); implicit nu punem date personale în header.
CONTACT = os.environ.get("HARTA_CONTACT", "").strip()
USER_AGENT = "harta-criminali-in-serie/0.1 (non-commercial educational map of documented serial killers" + (
    f"; contact: {CONTACT})" if CONTACT else ")"
) + " python-httpx"

# 1 cerere / secundă / domeniu (principiul 3)
MIN_INTERVAL_S = 1.0
