# Jurnal

## 2026-11-05 — Faza 0: schelet

- Repo git inițializat pe `main`; structura din secțiunea 4.3 a planului (module încă neimplementate pentru fazele 2–3 au doar docstring).
- Stack instalat: Python 3.12.10 (venv `.venv/`), Astro 7.4.5, MapLibre GL JS 6.16.0, basemap OpenFreeMap `positron`.
- Abatere: MapLibre 6 nu mai are export implicit, deci `import * as maplibregl from 'maplibre-gl'`.
- Abatere: `npm run dev` funcționează din rădăcină (package.json care deleagă la `site/`) și din `site/`.
- Deciziile D1–D6 au fost puse lui Marius; până la răspuns se folosesc valorile implicite din plan.
  Emailul lui Marius NU e pus în User-Agent; contactul se poate seta cu `HARTA_CONTACT`.
- Abatere: MapLibre 6 își caută worker-ul lângă bundle; în build Vite nu-l copiază, iar în dev pre-bundling-ul îi strică căile.
  Rezolvare: `optimizeDeps.exclude: ['maplibre-gl']`, `worker.format: 'es'` și `setWorkerUrl()` cu worker-ul importat prin `?worker&url`.
- Acceptare faza 0: `npm run dev` afișează harta lumii (verificat în browser, dev și `astro preview`); `python -m pipeline --help` răspunde.

## 2026-11-05 — Faza 1: Wikidata + Wikipedia

Cifre reale (din `data/coverage.json`):
- **Wikidata: 1.299 item-uri umane** cu ocupația/clasa „serial killer” (Q484188). Interogarea fără filtrul P31=Q5 dă 1.445;
  diferența de 146 sunt personaje fictive (film, benzi desenate, jocuri) și câteva grupuri/duo-uri, excluse.
  **Abatere de la plan:** planul estima „mii”; Wikidata are mult mai puține item-uri cu ocupația setată.
- **Listele Wikipedia** („by country” + sub-listele {{Main}} pentru SUA, Regatul Unit, Africa de Sud, Columbia, China, Chile;
  „by number of victims”; „before 1900”): 3.605 intrări, 1.903 titluri unice, 1.902 rezolvate la QID;
  **+807 persoane** umane fără ocupația setată în Wikidata (`inclusion: wikipedia-list`).
- **Total: 2.106 persoane**; 2.068 cu articol Wikipedia (1.984 în engleză).
- **Zonă de activitate:** 2.087 (99,1%) au cel puțin un punct; **1.943 (92,3%) la nivel ≤ admin1** (oraș/district/stat).
  **Criteriul de 95% NU e atins în faza 1.** Restul de 144 au doar țara (multe cazuri sovietice cu infobox „Soviet Union”
  fără state) sau nimic (19 fără articol și fără loc). Murderpedia („Location”) ar trebui să acopere o parte în faza 2.
- Naștere geocodată: 1.184; deces: 699. 111 țări cu cel puțin o persoană; pagini `/country/xx` pentru toate.
- Imagini: 455 din Wikimedia Commons (P18) cu licență liberă verificată; 2 respinse inițial (FAL, OGL) apoi acceptate ca libere.

Decizii și abateri:
- Locurile se rezolvă **doar prin Wikidata** (titlu Wikipedia -> item -> P625), fără Nominatim în faza 1.
- Straturi pentru zona de activitate, în ordine: infobox → introducere → secțiunile despre crime → restul corpului
  (fără biografie/proces/închisoare) → țară (infobox/introducere/listă/cetățenie). Detalii în METODOLOGIE.md.
- Clădirile (închisori, tribunale, spitale) sunt excluse din zona de activitate: apăreau ca locuri de detenție.
- Clasificarea locurilor: municipiile (comune, Gemeinde) nu sunt „human settlement” în Wikidata, deci au fost adăugate explicit;
  organizațiile prinse doar ca „geographic region” (ex. un minister) sunt ignorate.
- SPARQL: interogarea de clase folosește `hint:gearing "forward"`; loturile care expiră se împart automat. Wikidata a răspuns
  o dată cu 429; `Retry-After` e respectat.
- User-Agent: politica Wikimedia cere contact (403 fără). Implicit `https://github.com/motmar16`, suprascris cu `HARTA_CONTACT`.
  Emailul lui Marius nu e folosit.
- Metoda și tipul victimelor: etichete din cuvinte-cheie (categorii Wikipedia, infobox `weapons`). Acoperire mică în faza 1
  (341 cu metodă, 1.700 cu tip de victime); Murderpedia le completează în faza 2.
- Poze doar din Commons; fără poze pentru autori neidentificați și fără fișiere al căror nume sugerează victime.
