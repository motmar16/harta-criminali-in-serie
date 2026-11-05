"""Circuitul corecturilor manuale: Excel (BOM + „;”) -> mutare în fișierul permanent -> valori."""
from pipeline.build import qa


def test_corrections_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(qa, "QA_CSV", tmp_path / "locatii_de_verificat.csv")
    monkeypatch.setattr(qa, "FIX_CSV", tmp_path / "locatii_corectii.csv")
    qa.QA_CSV.write_text(
        "prioritate;id;nume;corectura;nota\n"
        "1;Q1;A;Bucharest;din articolul ro\n"
        "1;Q2;B;Q19660 | Yonkers, New York;\n"
        "3;Q3;C;OK;\n"
        "3;Q4;D;;\n", encoding="utf-8-sig")
    fixes = qa.load_corrections()
    assert fixes == {"Q1": ["Bucharest"], "Q2": ["Q19660", "Yonkers, New York"], "Q3": ["ok"]}
    # corecturile au fost mutate în fișierul permanent: rămân și după ce raportul e regenerat gol
    qa.QA_CSV.write_text("prioritate;id;nume;corectura;nota\n", encoding="utf-8-sig")
    assert qa.load_corrections() == fixes
    assert qa.FIX_CSV.read_text(encoding="utf-8-sig").startswith("id;locuri;nota")
