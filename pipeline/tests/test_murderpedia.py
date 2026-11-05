"""Teste pe HTML sintetic (scris de mână, în stilul paginilor Murderpedia, fără conținut real)."""
from pipeline.build.murderpedia_merge import legal_from_mp, split_location, title_candidates, victim_types_mp
from pipeline.normalize import dedupe
from pipeline.sources import murderpedia as m

PROFILE = """<html><head><title>Jane Q. Test | Murderpedia, the encyclopedia of murderers</title></head><body>
<table><tr><td><font>Classification: <b>Serial killer</b></font></td></tr>
<tr><td><font>Characteristics: <b>Poison<b>er</b></b></font></td></tr>
<tr><td>Number of victims:&nbsp;<b>3 - 5</b></td></tr>
<tr><td>Date of murders: <b>1950 - 1952</b></td></tr>
<tr><td>Date of birth: <b>March 3, 1920</b></td></tr>
<tr><td>Victim profile: <b>Her husbands, 60, 71 / A neighbour, 80</b></td></tr>
<tr><td>Method of murder: <b>Poisoning (arsenic)</b></td></tr>
<tr><td>Location: <b>Springfield, Illinois, USA</b></td></tr>
<tr><td>Status: <b>Sentenced to life in prison on May 1, 1953. Died in 1970</b></td></tr></table>
<p>Long narrative that must not be captured. Status: ignored.</p>
<img src="../images/test/photo.jpg"></body></html>"""


def test_parse_profile_fields_only():
    rec = m.parse_profile("https://murderpedia.org/female.T/t/test.htm", PROFILE)
    assert rec["classification"] == "Serial killer"
    assert rec["characteristics"] == "Poisoner"          # taguri inline în mijlocul cuvântului
    assert rec["victims"] == "3 - 5"
    assert rec["method"] == "Poisoning (arsenic)"
    assert rec["location"] == "Springfield, Illinois, USA"
    assert rec["status"].startswith("Sentenced to life")
    assert rec["has_photos"] is True
    assert "narrative" not in str(rec)
    assert m.is_serial(rec)


def test_split_location():
    cmap = {"usa": "US", "canada": "CA"}
    assert split_location("Montreal, Quebec/Calgary, Alberta, Canada", cmap)[2] == [["Montreal", "Quebec"], ["Calgary", "Alberta"]]
    iso, _, segs = split_location("Los Angeles/San Diego, California, USA", cmap)
    assert iso == "US" and segs == [["Los Angeles", "California"], ["San Diego", "California"]]
    assert title_candidates(["Yonkers", "Westchester County", "New York"], "USA")[0] == "Yonkers, New York"
    assert title_candidates(["New York"], "USA")[0] == "New York (state)"


def test_mp_derived_fields():
    rec = m.parse_profile("u", PROFILE)
    assert legal_from_mp(rec) == "convicted"
    assert "elderly" not in victim_types_mp(rec)        # vârste mixte
    assert "family" in victim_types_mp(rec)              # „husbands”
    assert legal_from_mp({"classification": "Serial killer ?", "status": "Sentenced"}) == "suspected"


def test_dedupe_decisions():
    killers = [
        {"id": "Q1", "names": {"primary": "Ralph Andrews", "aliases": []}, "birth": {"date": "1945-01-01"}, "countries": ["US"], "sources": {"active_area": "wikipedia-infobox"}},
        {"id": "Q2", "names": {"primary": "John Smith", "aliases": []}, "birth": {"date": "1901"}, "countries": ["GB"], "sources": {"active_area": "wikipedia-infobox"}},
        {"id": "Q3", "names": {"primary": "John Smith", "aliases": []}, "birth": None, "countries": ["US"], "sources": {"active_area": "wikipedia-infobox"}},
    ]
    mt = dedupe.Matcher(killers, {})
    rec = {"title": "Ralph Raymond Andrews | Murderpedia", "index_name": "Ralph Raymond ANDREWS", "date_of_birth": "1945"}
    assert dedupe.decide(mt.candidates(rec, "US")) == ("match", "Q1")
    # anul de naștere contrazice -> nu e aceeași persoană
    rec2 = {"title": "Ralph Andrews | Murderpedia", "index_name": "Ralph ANDREWS", "date_of_birth": "1970"}
    assert dedupe.decide(mt.candidates(rec2, "US"))[0] == "none"
    # doi „John Smith” fără an care să decidă, țara exclude unul
    rec3 = {"title": "John Smith | Murderpedia", "index_name": "John SMITH", "date_of_birth": None}
    assert dedupe.decide(mt.candidates(rec3, "US")) == ("match", "Q3")
    rec4 = {"title": "John Smith | Murderpedia", "index_name": "John SMITH", "date_of_birth": None}
    assert dedupe.decide(mt.candidates(rec4, None))[0] == "ambiguous"
