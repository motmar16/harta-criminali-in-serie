# Harta criminalilor în serie

Site static cu o hartă interactivă a lumii pe care apar criminalii în serie documentați, cu sursă pentru fiecare fapt.
Coloana vertebrală e Wikidata + Wikipedia (licențe libere); Murderpedia urmează în faza 2 (doar câmpuri structurate).
Planul complet: [PLAN-OPUS-5.5.md](PLAN-OPUS-5.5.md). Jurnal de decizii: [docs/JURNAL.md](docs/JURNAL.md).

## Cerințe

- Python 3.12+
- Node.js 20+ (testat cu 24)

## Pornire

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # pe Linux/macOS: .venv/bin/python
npm --prefix site install
```

Date (refăcute din cache-ul local `data/raw/` când există; altfel descărcate politicos, 1 cerere/secundă):

```bash
.venv/Scripts/python -m pipeline all          # Wikidata, Wikipedia, Commons, build (minute, din cache)
.venv/Scripts/python -m pipeline murderpedia  # manual; prima dată ~2 ore (6.900 pagini la 1 cerere/s), apoi din cache
.venv/Scripts/python -m pipeline build        # reface data/ din tot ce e în cache
```

Cazurile Murderpedia ↔ Wikidata neclare ajung în `data/validare/dedupe_ambigue.csv`; completează coloana `decizie`
(QID-ul corect, `nou` sau `diferit`) și rulează din nou `build`.

Site:

```bash
npm run dev      # http://localhost:4321
npm run build    # site/dist/
```

Opțional: `HARTA_CONTACT=<email sau URL>` adaugă un contact în User-Agent-ul folosit pentru Wikimedia.

## Structură

- `pipeline/` codul Python (surse, normalizare, geocodare, export)
- `data/` date extrase (JSON) și `coverage.json`; `data/raw/` e cache brut, **nu intră în git**
- `site/` Astro + MapLibre GL JS, basemap OpenFreeMap; `site/public/data/` e generat de pipeline
- `docs/` jurnal, metodologie, surse

## Licențe date

Textele și faptele din Wikipedia: CC BY-SA 4.0, cu atribuire și link la revizie. Wikidata: CC0.
Hărți: © OpenStreetMap contributors, OpenFreeMap.
