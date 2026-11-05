"""Wikipedia: articolele persoanelor (infobox + introducere) și listele de criminali în serie.

Ce se păstrează în repo: doar faptele extrase (câmpuri infobox, titluri de locuri, categorii relevante).
Wikitext-ul brut stă în data/raw/wikipedia/ (gitignored).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import mwparserfromhell as mw

from pipeline import http
from pipeline.config import RAW
from pipeline.sources import mediawiki, wikidata

log = logging.getLogger(__name__)

LISTS = [
    "List of serial killers by country",
    "List of serial killers by number of victims",
    "List of serial killers before 1900",
]
# alte limbi, în ordinea preferinței, pentru persoanele fără articol în engleză
FALLBACK_LANGS = ["de", "fr", "es", "it", "ru", "pt", "pl", "nl", "uk", "cs", "sv", "ja", "zh", "tr", "fi", "hu",
                  "ro", "ko", "he", "ar", "fa", "id", "ca", "no", "da", "sr", "hr", "bg", "el"]

INFOBOX_PREFERRED = ("infobox criminal", "infobox serial killer", "infobox murderer", "infobox spree killer")
LOCATION_FIELDS = ["locations", "location", "cities", "city", "states", "state", "region", "country", "countries"]
OTHER_FIELDS = ["victims", "begin_year", "beginyear", "end_year", "endyear", "years_active", "apprehended",
                "convictions", "conviction", "criminal_penalty", "penalty", "criminal_status", "conviction_status",
                "criminal_charges", "motive", "weapons"]
SKIP_SECTIONS = ("see also", "references", "notes", "cited works", "bibliography", "further reading",
                 "external links", "sources", "explanatory notes", "footnotes")
NON_ARTICLE_NS = ("file:", "image:", "category:", "wikt:", "wiktionary:", "help:", "wikipedia:", "wp:",
                  "template:", "portal:", "s:", "commons:", ":file:", "media:", "special:", "user:", "talk:")


# ---------------------------------------------------------------- utilitare wikitext

def _links(code: Any) -> list[str]:
    out = []
    for link in code.filter_wikilinks(recursive=True):
        t = str(link.title).strip()
        if not t or t.lower().startswith(NON_ARTICLE_NS) or re.match(r"^[a-z]{2,3}:", t):
            continue
        out.append(t)
    return out


def _plain(code: Any) -> str:
    """Text simplu, fără referințe, comentarii și șabloane (în afară de liste și steaguri)."""
    code = mw.parse(str(code))
    for tag in code.filter_tags(recursive=True):
        if str(tag.tag).lower() in ("ref", "sup", "small"):
            try:
                code.remove(tag)
            except ValueError:
                pass
    for c in code.filter_comments(recursive=True):
        try:
            code.remove(c)
        except ValueError:
            pass
    text = str(code)
    text = re.sub(r"<br\s*/?>", ", ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return text


FLAG_TEMPLATES = ("flag", "flagcountry", "flagu", "flagicon", "flag country", "flagdeco")


def field_places(value: Any) -> tuple[list[str], list[str]]:
    """Dintr-o valoare de infobox: (titluri legate, fragmente de text simplu care pot fi nume de locuri)."""
    code = mw.parse(str(value))
    titles = _links(code)
    for tpl in code.filter_templates(recursive=True):
        name = str(tpl.name).strip().lower()
        if name in FLAG_TEMPLATES and tpl.params:
            titles.append(str(tpl.params[0].value).strip())
    # restul, ca text: scoatem linkurile și șabloanele, împărțim pe separatori
    rest = mw.parse(str(code))
    for node in rest.filter_wikilinks(recursive=False) + rest.filter_templates(recursive=False):
        try:
            rest.remove(node)
        except ValueError:
            pass
    text = _plain(rest)
    text = re.sub(r"\([^)]*\)", " ", text)
    chunks = []
    for part in re.split(r",|;|/|\band\b|\bor\b|\blater\b|\bthen\b|\n|&", text):
        part = re.sub(r"\s+", " ", part).strip(" .:*'\"-–")
        if 2 < len(part) < 40 and part[:1].isupper() and len(part.split()) <= 4 and not re.search(r"\d", part):
            chunks.append(part)
    return titles, chunks


def find_infobox(code: Any) -> Any | None:
    boxes = [t for t in code.filter_templates(recursive=True) if str(t.name).strip().lower().startswith("infobox")]
    for t in boxes:
        if str(t.name).strip().lower().split("<!--")[0].strip() in INFOBOX_PREFERRED:
            return t
    return boxes[0] if boxes else None


def parse_infobox(wikitext: str) -> dict[str, Any]:
    code = mw.parse(wikitext)
    ib = find_infobox(code)
    if ib is None:
        return {}
    out: dict[str, Any] = {"template": str(ib.name).strip().split("<!--")[0].strip()}
    for f in LOCATION_FIELDS:
        if ib.has(f) and str(ib.get(f).value).strip():
            titles, chunks = field_places(ib.get(f).value)
            if titles or chunks:
                out[f] = {"titles": titles, "text": chunks}
    for f in OTHER_FIELDS:
        if ib.has(f):
            v = re.sub(r"\s+", " ", _plain(ib.get(f).value)).strip(" ,")
            v = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", v)
            v = re.sub(r"\{\{[^{}]*\}\}", "", v).strip(" ,")
            if v:
                out[f] = v[:300]
    return out


def lead_links(wikitext: str, limit: int = 60) -> list[str]:
    """Linkurile din introducere (înainte de primul titlu de secțiune), fără infobox/șabloane/paranteze.

    Parantezele se elimină fiindcă, în multe limbi, conțin locul nașterii/morții, nu zona crimelor.
    """
    lead = re.split(r"^==[^=].*$", wikitext, maxsplit=1, flags=re.M)[0]
    code = mw.parse(lead)
    for tpl in code.filter_templates(recursive=False):
        try:
            code.remove(tpl)
        except ValueError:
            pass
    text = _plain(code)
    # protejăm linkurile (pot conține paranteze în titlu), apoi scoatem parantezele
    store: list[str] = []
    text = re.sub(r"\[\[[^\[\]]*\]\]", lambda m: f"\x00{store.append(m.group(0)) or len(store) - 1}\x00", text)
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\([^()]*\)", " ", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], text)
    return _links(mw.parse(text))[:limit]


CRIME_SECTION = re.compile(r"murder|crime|killing|victim|attack|poisoning|case|investigation|modus|series", re.I)
NON_CRIME_SECTION = re.compile(r"early life|childhood|background|biography|personal|family|aftermath|legacy|"
                               r"popular culture|media|film|book|see also|reference|note|external|further|"
                               r"bibliography|imprisonment|death|execution|later life|trial|appeal", re.I)


def crime_section_links(wikitext: str, limit: int = 120, crime: bool = True) -> list[str]:
    """Linkurile din secțiunile despre crime („Murders”, „Crimes”, „Victims”…), nu din biografie.

    Cu crime=False: linkurile din celelalte secțiuni neutre (nici biografie, nici proces/închisoare/media).
    """
    parts = re.split(r"^(==+)\s*(.*?)\s*\1\s*$", wikitext, flags=re.M)
    out: list[str] = []
    # parts = [lead, '==', titlu, corp, '==', titlu, corp, …]
    for i in range(1, len(parts) - 2, 3):
        heading, body = parts[i + 1], parts[i + 2]
        if bool(CRIME_SECTION.search(heading)) == crime and not NON_CRIME_SECTION.search(heading):
            code = mw.parse(body)
            for tag in code.filter_tags(recursive=True):
                if str(tag.tag).lower() == "ref":
                    try:
                        code.remove(tag)
                    except ValueError:
                        pass
            out += _links(code)
    return out[:limit]


def categories(wikitext: str) -> list[str]:
    return [c.strip() for c in re.findall(r"\[\[\s*Category\s*:\s*([^|\]]+)", wikitext, flags=re.I)]


def first_paragraph(wikitext: str) -> str:
    """Primul paragraf al introducerii, ca text simplu (pentru rezumatul CC BY-SA cu atribuire)."""
    lead = re.split(r"^==[^=].*$", wikitext, maxsplit=1, flags=re.M)[0]
    code = mw.parse(lead)
    for tpl in code.filter_templates(recursive=False):
        try:
            code.remove(tpl)
        except ValueError:
            pass
    for link in code.filter_wikilinks(recursive=False):
        t = str(link.title).strip().lower()
        if t.startswith(("file:", "image:", "category:")):
            try:
                code.remove(link)
            except ValueError:
                pass
    text = _plain(code)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    paras = [re.sub(r"\s+", " ", p).strip() for p in text.split("\n\n")]
    paras = [p for p in paras if len(p) > 80 and not p.startswith(("{", "|", "!"))]
    if not paras:
        return ""
    # paranteza de după nume (date, pronunție) iese ciuntită după scoaterea șabloanelor; o eliminăm
    text = re.sub(r"^([^(]{0,150}?)\s*\([^()]*\)", r"\1", paras[0], count=1)
    return re.sub(r"\s+([,.;])", r"\1", text)


# ---------------------------------------------------------------- liste

def fetch_list(title: str, refresh: bool = False) -> dict[str, Any]:
    pages = mediawiki.fetch_pages("en", [title], refresh=refresh)
    return pages[title]


def _row_country_names(cell: str) -> list[str]:
    titles, chunks = field_places(cell)
    codes = []
    for tpl in mw.parse(cell).filter_templates(recursive=True):
        n = str(tpl.name).strip()
        if re.fullmatch(r"[A-Z]{3}", n):  # {{COL}}, {{USA}}: coduri de țară (IOC / ISO alpha-3)
            codes.append(n)
    return titles + chunks + [f"code:{c}" for c in codes]


def parse_list(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Intrări {title, list, section, country_names, source_url} dintr-o listă (marcatori sau tabel)."""
    txt = page.get("wikitext") or ""
    src = f"https://en.wikipedia.org/w/index.php?title={page['title'].replace(' ', '_')}&oldid={page['revid']}"
    out: list[dict[str, Any]] = []
    h2 = h3 = ""
    in_table = False
    row: list[str] = []

    def flush_row() -> None:
        cells = [c for c in row if c.strip()]
        if len(cells) >= 2:
            names = _links(mw.parse(cells[0]))
            if names:
                out.append({"title": names[0], "list": page["title"], "section": h2,
                            "country_names": _row_country_names(cells[1]), "source_url": src})

    for line in txt.split("\n"):
        m = re.match(r"^(=+)\s*(.*?)\s*=+\s*$", line)
        if m:
            level = len(m.group(1))
            if level == 2:
                h2, h3 = m.group(2), ""
            elif level == 3:
                h3 = m.group(2)
            continue
        if line.startswith("{|"):
            in_table, row = True, []
            continue
        if in_table:
            if line.startswith("|}"):
                flush_row()
                in_table, row = False, []
            elif line.startswith("|-"):
                flush_row()
                row = []
            elif line.startswith("|") and not line.startswith("|+"):
                # o celulă per linie, sau mai multe separate prin ||
                for cell in line[1:].split("||"):
                    # „style=... | conținut”
                    if "|" in cell and not cell.strip().startswith(("[[", "{{")) and "=" in cell.split("|")[0]:
                        cell = cell.split("|", 1)[1]
                    row.append(cell)
            elif row:
                row[-1] += "\n" + line
            continue
        if re.match(r"^\*[^*]", line) and h2 and not h2.lower().startswith(SKIP_SECTIONS):
            head = line.split(":", 1)[0] if "]]:" in line or "]] :" in line else line[:200]
            names = _links(mw.parse(head))
            if names:
                out.append({"title": names[0], "list": page["title"], "section": h2,
                            "country_names": [h3] if h3 else [], "source_url": src})
    return out


def main_sublists(page: dict[str, Any]) -> list[str]:
    """Paginile {{Main|...}} spre care lista „by country” trimite conținutul unei țări (ex. SUA)."""
    out = []
    for tpl in mw.parse(page.get("wikitext") or "").filter_templates(recursive=False):
        if str(tpl.name).strip().lower() == "main" and tpl.params:
            t = str(tpl.params[0].value).strip()
            if t.lower().startswith("list of serial killers in"):
                out.append(t)
    return out


def collect_list_entries(refresh: bool = False) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for title in LISTS:
        page = fetch_list(title, refresh=refresh)
        entries += parse_list(page)
        if title.endswith("by country"):
            for sub in main_sublists(page):
                sp = fetch_list(sub, refresh=refresh)
                if sp.get("wikitext"):
                    country = re.sub(r"^List of serial killers in (the )?", "", sp["title"])
                    for e in parse_list(sp):
                        e["country_names"] = e["country_names"] or [country]
                        e["section"] = e["section"] or "Convicted serial killers by country"
                        entries.append(e)
    log.info("Liste Wikipedia: %d intrări", len(entries))
    return entries


# ---------------------------------------------------------------- articole

def article_ref(person: dict[str, Any]) -> tuple[str, str] | None:
    """(limbă, titlu) al articolului folosit: engleză, altfel prima limbă disponibilă din FALLBACK_LANGS."""
    links = {}
    for s in person["claims"].get("sitelink", []):
        wiki, title = s.split("|", 1)
        m = re.match(r"https://([a-z\-]+)\.wikipedia\.org/", wiki)
        if m:
            links[m.group(1)] = title
    for lang in ["en", *FALLBACK_LANGS]:
        if lang in links:
            return lang, links[lang]
    if links:
        lang = sorted(links)[0]
        return lang, links[lang]
    return None


def extract_article(page: dict[str, Any]) -> dict[str, Any]:
    wt = page.get("wikitext") or ""
    return {
        "lang": page["lang"], "title": page["title"], "revid": page.get("revid"),
        "retrieved_at": page.get("retrieved_at"),
        "url": f"https://{page['lang']}.wikipedia.org/wiki/{page['title'].replace(' ', '_')}",
        "source_url": f"https://{page['lang']}.wikipedia.org/w/index.php?"
                      f"title={page['title'].replace(' ', '_')}&oldid={page.get('revid')}",
        "infobox": parse_infobox(wt) if page["lang"] == "en" else {},
        "lead_links": lead_links(wt),
        "crime_links": crime_section_links(wt) if page["lang"] == "en" else [],
        "body_links": crime_section_links(wt, crime=False) if page["lang"] == "en" else [],
        "categories": categories(wt),
        "summary": first_paragraph(wt) if page["lang"] == "en" else "",
    }


def run(refresh: bool = False) -> None:
    """Adaugă persoanele din liste lipsă din Wikidata, apoi extrage infobox + introducere pentru toți."""
    from pipeline.geocode import wikidata_places as wp

    people = wikidata.load_people()
    entries = collect_list_entries(refresh=refresh)
    qids = wp.titles_to_qids("en", [e["title"] for e in entries])
    for e in entries:
        e["qid"] = qids.get(wp.clean_title(e["title"]))
    candidates = sorted({e["qid"] for e in entries if e["qid"] and e["qid"] not in people}, key=lambda q: int(q[1:]))
    log.info("Liste: %d intrări cu QID, %d persoane noi candidate", sum(1 for e in entries if e["qid"]), len(candidates))
    if candidates:
        details = wikidata.fetch_details(candidates, refresh=refresh)
        added = 0
        for q, p in details.items():
            if "Q5" in p["claims"].get("P31", []):  # doar oameni (nu articole despre cazuri sau grupuri)
                p["origin"] = "wikipedia-list"
                people[q] = p
                added += 1
        log.info("Liste: %d persoane adăugate (oameni fără ocupația serial killer în Wikidata)", added)
    wikidata.save_people(people)
    (RAW / "wikipedia").mkdir(parents=True, exist_ok=True)
    (RAW / "wikipedia" / "list_entries.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")

    # articole: grupate pe limbă, ca să meargă pe loturi de 50
    by_lang: dict[str, list[str]] = {}
    refs = {}
    for q, p in people.items():
        ref = article_ref(p)
        if ref:
            refs[q] = ref
            by_lang.setdefault(ref[0], []).append(ref[1])
    articles = {}
    for lang, titles in sorted(by_lang.items(), key=lambda kv: -len(kv[1])):
        pages = mediawiki.fetch_pages(lang, titles, refresh=refresh)
        for q, (l, t) in refs.items():
            if l == lang and pages.get(t) and not pages[t].get("missing"):
                articles[q] = extract_article(pages[t])
    (RAW / "wikipedia" / "articles.json").write_text(json.dumps(articles, ensure_ascii=False), encoding="utf-8")
    log.info("Wikipedia gata: %d articole extrase (%s)", len(articles),
             ", ".join(f"{l}:{len(t)}" for l, t in sorted(by_lang.items(), key=lambda kv: -len(kv[1]))[:8]))


def load_articles() -> dict[str, dict[str, Any]]:
    return json.loads((RAW / "wikipedia" / "articles.json").read_text(encoding="utf-8"))


def load_list_entries() -> list[dict[str, Any]]:
    return json.loads((RAW / "wikipedia" / "list_entries.json").read_text(encoding="utf-8"))
