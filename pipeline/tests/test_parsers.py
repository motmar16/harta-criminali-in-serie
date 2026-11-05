"""Teste pe fragmente de wikitext sintetice (scrise de mână, nu copiate din articole)."""
from pipeline.normalize import dates
from pipeline.normalize.names import slugify
from pipeline.normalize.places import jitter, parse_victims
from pipeline.sources import wikipedia as w

ARTICLE = """{{Short description|Fictional test person}}
{{Infobox criminal
| name = Test Person
| victims = 22–29<ref>x</ref>
| country = United States and [[Canada]]
| states = {{hlist|[[California]]|[[Washington (state)|Washington]]}}
| begin_year = February 1926
| end_year = June 9, 1927
| penalty = [[Death penalty|Death]]
}}
'''Test Person''' (born in [[Springfield, Illinois]]; 1897 – 1928) was an American [[serial killer]] who murdered
women in [[San Francisco]] and [[Portland, Oregon|Portland]] (later moving to [[Winnipeg]]).

== Early life ==
He grew up in [[Boston]].
[[Category:Unidentified serial killers]]
"""


def test_infobox_fields():
    ib = w.parse_infobox(ARTICLE)
    assert ib["template"].lower() == "infobox criminal"
    assert ib["states"]["titles"] == ["California", "Washington (state)"]
    assert "Canada" in ib["country"]["titles"]
    assert "United States" in ib["country"]["text"]
    assert ib["victims"].startswith("22–29")
    assert ib["penalty"] == "Death"


def test_lead_links_skip_parentheses_and_sections():
    links = w.lead_links(ARTICLE)
    assert "San Francisco" in links and "Portland, Oregon" in links
    assert "Springfield, Illinois" not in links  # în paranteză
    assert "Winnipeg" not in links               # în paranteză
    assert "Boston" not in links                 # după primul titlu de secțiune


def test_categories_and_summary():
    assert "Unidentified serial killers" in w.categories(ARTICLE)
    summary = w.first_paragraph(ARTICLE)
    assert summary.startswith("Test Person was an American serial killer")
    assert "[[" not in summary and "{{" not in summary


def test_list_parsing_bullets_and_tables():
    page = {"title": "List X", "revid": 1, "wikitext": """
== Convicted serial killers by country ==
=== Austria ===
* [[Jane Roe]]: killed four people in [[Vienna]].
== Table ==
{| class="wikitable"
! Name !! Country
|-
| [[John Doe (criminal)|John Doe]]
| {{flag|Peru}}
|-
| [[Max Mustermann]] || [[Germany]]
|}
== See also ==
* [[Something else]]
"""}
    entries = w.parse_list(page)
    by_title = {e["title"]: e for e in entries}
    assert by_title["Jane Roe"]["country_names"] == ["Austria"]
    assert "Peru" in by_title["John Doe (criminal)"]["country_names"]
    assert "Germany" in by_title["Max Mustermann"]["country_names"]
    assert "Something else" not in by_title


def test_victims():
    v = parse_victims("22–29")
    assert (v["proven"], v["possible"]) == (22, 29)
    v = parse_victims("36 confirmed, 43 confessed, 55+ estimated")
    assert (v["proven"], v["possible"]) == (36, 55)
    v = parse_victims("4 (in 1990)")
    assert (v["proven"], v["possible"]) == (4, None)
    v = parse_victims("10+", ["12"])
    assert v["proven"] == 12 and v["source"] == "wikidata"
    assert parse_victims(None) is None


def test_dates():
    assert dates.wikidata_time({"time": "+1936-10-16T00:00:00Z", "precision": 11}) == {"date": "1936-10-16", "precision": "day"}
    assert dates.wikidata_time({"time": "+1936-00-00T00:00:00Z", "precision": 9})["date"] == "1936"
    assert dates.active_period("May 1971", "December 1985") == {"start": "1971", "end": "1985"}
    assert dates.active_period("144", "116 BC") == {"start": "-144", "end": "-116"}


def test_slug_and_jitter():
    assert slugify("Андрей Чикатило") == "andrei-chikatilo"
    assert slugify("Oleg Kuznetsov (serial killer)") == "oleg-kuznetsov"
    a = jitter(50.0, 10.0, "Q1-a01", "admin1")
    assert a == jitter(50.0, 10.0, "Q1-a01", "admin1")  # determinist
    assert a != (50.0, 10.0)
    assert jitter(50.0, 10.0, "Q1-a01", "address") == (50.0, 10.0)


def test_crime_section_links():
    text = ("lead\n== Early life ==\nborn in [[Boston]]\n== Murders ==\nIn [[Salem, Massachusetts|Salem]] he killed."
            "<ref>[[Nope]]</ref>\n=== Victims ===\n[[Lynn, Massachusetts]]\n== Trial ==\n[[Concord]]")
    assert w.crime_section_links(text) == ["Salem, Massachusetts", "Lynn, Massachusetts"]
