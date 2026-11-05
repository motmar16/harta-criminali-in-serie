# Verificarea manuală a locațiilor

Fișierul de lucru: `data/validare/locatii_de_verificat.csv` (se deschide direct în Excel; separator „;”).
Se regenerează la fiecare `python -m pipeline build`, dar **ce completezi nu se pierde**: build-ul mută întâi
corecturile în `data/validare/locatii_corectii.csv` (fișierul permanent), apoi rescrie raportul.

## Ordinea recomandată

| prioritate | motiv | ce înseamnă |
|---|---|---|
| 1 | `fara_locatie`, `doar_tara` | nu știm unde au avut loc crimele; punctul e în centrul țării sau lipsește |
| 2 | `sursa_slaba` | locul vine dintr-o sursă euristică (link oarecare din articol, cetățenie) |
| 3 | `zona_egala_cu_nasterea` | zona găsită e chiar orașul natal; adesea corect (au ucis acasă), dar de confirmat |

Coloanele utile: `zona_actuala`, `sursa_zonei`, `nascut_in`, `murderpedia_location` și linkurile
(`wikipedia`, `murderpedia`, `radford`, `wikidata`).

## Ce scrii în coloana `corectura`

- **locul corect**, ca titlu de articol Wikipedia în engleză: `Bucharest`, `Rostov Oblast`, `Yonkers, New York`;
- **mai multe locuri**, separate prin `|`: `Utah | Colorado`;
- sau un **ID Wikidata** (sigur, fără ambiguitate): `Q19660`;
- **`ok`** dacă locația actuală e corectă: cazul dispare din listă.

Coloana `nota` e opțională (de unde ai luat informația). Regula de bază: zona în care au avut loc crimele, nu locul
nașterii, al arestării sau al închisorii. Dacă nu se poate afla, lasă rândul gol.

## După completare

Salvează fișierul (păstrează formatul CSV) și rulează:

```bash
.venv/Scripts/python -m pipeline build
```

Corecturile apar pe site cu sursa „manual correction”. Un loc nerecunoscut e semnalat în log
(„nu e un loc recunoscut”); atunci folosește ID-ul Wikidata.
