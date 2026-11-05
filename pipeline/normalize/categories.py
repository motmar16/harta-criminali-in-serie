"""Categorii pentru filtre: metoda și tipul victimelor, din cuvinte-cheie.

Intrări: categoriile Wikipedia, câmpurile infobox `weapons`/`motive`, și (faza 2) câmpurile Murderpedia
„Method of murder”, „Victim profile”, „Characteristics”. Se exportă doar etichetele, nu textul sursă
(„Victim profile” poate conține nume de victime; principiul 6).
"""
from __future__ import annotations

import re

METHOD = {
    "shooting": r"shoot|shot\b|gun|rifle|pistol|revolver|firearm|shotgun|firing squad",
    "stabbing": r"stab|knife|knives|blade|machete|axe\b|hatchet|cutting|slash|dagger|sword",
    "strangulation": r"strangl|garrot|throttl|ligature|hanging them|neck",
    "poisoning": r"poison|arsenic|cyanide|strychnine|insulin|overdose|injection of|thallium|digoxin|potassium chloride",
    "beating": r"beat|bludgeon|blunt|hammer|club\b|bat\b|rock|stone|brick|crush",
    "suffocation": r"suffocat|smother|asphyx",
    "arson": r"arson|burn|fire\b|set on fire",
    "drowning": r"drown",
}
VICTIM = {
    # fără „male”/„female”: în categorii descriu de obicei făptașul („Male murderers”)
    "women": r"women|woman|girls?\b|wives|femicide|matricide",
    "men": r"\bmen\b|homosexual|gay\b|husbands",
    "children": r"child|infant|bab(y|ies)|boys?\b|girls?\b|teen|minor|filicide|infanticide|students?\b|aged \d\b|aged 1[0-5]\b",
    "elderly": r"elderly|old women|old men|old people|pensioner|retiree|senior",
    "sex workers": r"prostitut|sex worker|escort",
    "patients": r"patient|nurse|hospital|medical serial|physician|doctor|care home|nursing home",
    "family": r"family|relative|wife|wives|husband|son\b|daughter|mother|father|parricide|filicide|uxoricide|mariticide|familicide|spouse",
    "travelers": r"hitchhik|traveler|traveller|tourist|motorist|truck|lodger|guest|innkeeper|passeng",
    "homeless": r"homeless|vagrant|drifter|street child",
}
_METHOD = {k: re.compile(v, re.I) for k, v in METHOD.items()}
_VICTIM = {k: re.compile(v, re.I) for k, v in VICTIM.items()}


def methods(*texts: str | None) -> list[str]:
    t = " | ".join(x for x in texts if x)
    return [k for k, rx in _METHOD.items() if rx.search(t)]


def victim_types(*texts: str | None) -> list[str]:
    t = " | ".join(x for x in texts if x)
    return [k for k, rx in _VICTIM.items() if rx.search(t)]


def wiki_category_hints(categories: list[str]) -> str:
    """Doar categoriile relevante (crime/victime/metodă), ca să nu prindem „People from X” etc."""
    keep = re.compile(r"murder|killer|poison|violence|filicide|uxoricide|mariticide|parricide|matricide|"
                      r"infanticide|familicide|shooting|stabbing|strangl|arson|rape|prostitut|nurse|medical", re.I)
    return " | ".join(c for c in categories if keep.search(c))
