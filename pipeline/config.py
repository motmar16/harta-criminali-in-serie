"""Căi și setări comune pentru pipeline."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"  # cache brut, gitignored (principiul 5)
SITE_DATA = ROOT / "site" / "public" / "data"
GEOCODE_CACHE = ROOT / "pipeline" / "geocode" / "cache.sqlite"

# User-Agent explicit (principiul 3). Politica Wikimedia cere un contact (URL sau email),
# altfel răspunde 403. Implicit: profilul GitHub public al proiectului; se suprascrie cu HARTA_CONTACT.
CONTACT = os.environ.get("HARTA_CONTACT", "").strip() or "https://github.com/motmar16"
USER_AGENT = (f"harta-criminali-in-serie/0.1 ({CONTACT}; non-commercial educational map of documented serial killers)"
              " python-httpx")

# 1 cerere / secundă / domeniu (principiul 3)
MIN_INTERVAL_S = 1.0
