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

## 2026-11-05 — Faza 2 (Murderpedia), spree killers, verificare încrucișată, locații

Marius a cerut, pe parcurs: Murderpedia, interfață light/dark cu filtre și poze, surse multiple, spree killers,
verificare din alte surse ca să nu ratăm criminali, locația corectă a fiecărui punct, fără sex la neidentificați.

Murderpedia:
- Crawl unic, 1 cerere/s: 6.890 profiluri în indexuri, **6.886 parsate**, 4 lipsă (404), 128 de minute. HTML doar în `data/raw/`.
- Clasificare Murderpedia: **852 „Serial killer”, 150 „Spree killer”**; restul (~5.900) sunt omoruri simple, crime în masă etc.
- Potrivire cu Wikidata/Wikipedia: 709 din 852 „serial” potrivite (83%); **291 de persoane noi** (212 serial + 79 spree);
  363 profiluri non-seriale folosite doar la îmbogățire (an naștere confirmat); **2 ambigue (0,2%)** în
  `data/validare/dedupe_ambigue.csv`. Criteriul fazei 2 (≤ 2% ambigue, ≥ 6.500 parsate) e îndeplinit.
- Corecturi după verificare: o potrivire greșită (Alexander Komin, Rusia ↔ un Komin din SUA) a dus la regula că țara
  trebuie să fie compatibilă; „Status” și „Characteristics” conțineau nume de victime, deci nu se mai publică.

Spree killers: Wikidata Q1154323 (96) + Murderpedia (150). „Category:Spree killers” nu mai există pe Wikipedia engleză.
Pe hartă au contur violet și filtru „Type”.

Verificare încrucișată (criminali ratați): arborele de categorii „Serial killers” din Wikipedia engleză a adus
**+432 de persoane** și **+65 de cazuri cu autor neidentificat** (ex. „Highway of Tears”). Interogarea Wikidata pe
descrieri („serial killer” în descriere, fără ocupație) expiră pe server; nu a putut fi folosită.

Locații (cazul Marius Csampar, pus „în Cluj”): de fapt avea doar țara (cetățenie), desenată lângă centrul României.
Reparat prin: linkuri din **propozițiile despre crime, în orice limbă** („Crimele sale s-au desfășurat … în
[[București]]”); „Location” din Murderpedia peste sursele euristice și când zona = locul nașterii; rafinare stat → oraș
cu Murderpedia; țara dominantă la sursele euristice; continentele și republicile sovietice nu mai trec drept zonă;
punctele „doar țară” sunt marcate explicit în tooltip și în fișă. Raport de verificare:
`data/validare/locatii_de_verificat.csv` (341 rânduri); corecturi manuale în `data/validare/locatii_corectii.csv`.

Neidentificați: 132; fără sex (Wikidata pune „male” la Jack the Ripper/Zodiac), fără poză, gri pe hartă.

Cifre finale (`data/coverage.json`):
- **2.966 persoane**: 2.756 serial, 156 spree, 54 ambele; 117 țări.
- Incluși prin: ocupație Wikidata 1.378, liste Wikipedia 800, categorii Wikipedia 432 + 65 cazuri, Murderpedia 291.
- Zonă de activitate: 2.938 au punct; **2.789 (94,0%) la nivel ≤ admin1** (1.309 oraș, 1.480 stat/regiune),
  149 doar țară, 28 fără locație. Ținta de 95% rămâne ușor sub; restul e de obicei fără loc în nicio sursă.
- Link Murderpedia: 1.358; poze Commons: 523; cu metodă: 1.289; cu tip de victime: 2.171.
- Statut: 2.497 condamnați, 227 neverificat, 132 neidentificați, 53 suspecți, 43 decedați înainte de proces, 14 achitați.

## 2026-11-05 (seara) — Radford, mass murderers, corectarea locațiilor

Cereri Marius: surse noi pentru cele 341 de locații de verificat; Radford are de fapt pagini per criminal
(„Serial Killer Timelines”, PDF); Columbine lipsea.

**Radford:** abaterea din plan era greșită: pe lângă baza completă (nepublică), cursul Psyc 405 publică 190 de cronologii
PDF. Descărcate o dată (1 cerere/s, `data/raw/radford/`), **146 potrivite cu persoane** → link direct la PDF pe fișă;
din 173 de PDF-uri s-au extras locuri din rândurile despre crime. Textul nu se copiază.

**Mass murderers (Columbine):** Harris și Klebold sunt „mass murderer” (un singur eveniment), nu „spree killer”.
Adăugat al treilea tip, din Wikidata (Q15883433, Q107565466), arborele Wikipedia „Mass murderers” și Murderpedia
(„Mass murderer”, 545 profiluri). Din arborele Wikipedia s-au exclus **517 militari / criminali de război / politicieni**
(feldmareșali, ofițeri SS, guvernatori coloniali). Duo-urile („Eric Harris and Dylan Klebold”) sunt o singură intrare.

**Locații – surse noi:**
- articolul evenimentului din Wikidata (P276/P131/P625), doar primul eveniment legat: 166 de persoane (Whitman → turnul
  universității, Cho → Virginia Tech);
- propozițiile despre crime din articolele în alte limbi (ru, uk, de, fr…), pentru cazurile semnalate (listă cumulativă
  în `data/validare/tinte_alte_limbi.txt`);
- textul intrărilor din listele Wikipedia („… on the road from [[Kabul]] to [[Jalalabad]]”);
- cronologiile Radford.
- **Bug important găsit:** la cazurile sovietice, infobox-ul spune „Soviet Union” (SU), iar orașele sunt în RU/UA/BY; testul
  de consecvență a țării le respingea pe toate. Acum URSS/Iugoslavia/Cehoslovacia/RDG acceptă statele succesoare.
- Parantezele din propoziții (locul nașterii în articolele rusești) se scot.
- Bug de unealtă: editările făcute prin heredoc în Git Bash înjumătățeau `\`, ceea ce a produs regex-uri stricate
  (`\b`, `\1`) și octeți nuli; toate găsite și reparate, verificate cu teste și citire directă.

Rezultat pe cele 341: **104 rezolvate**; rămân 237 (94 „zona = locul nașterii”, adesea corecte, 86 doar țară, 32 sursă
slabă, 26 fără locație).

Cifre (`data/coverage.json`): **3.893 de persoane** (2.810 serial, 976 mass, 211 spree; unele au mai multe tipuri),
132 de țări; zonă la nivel ≤ admin1: **95,9%** (2.060 oraș, 1.635 stat/regiune, 37 adresă exactă, 127 doar țară,
34 fără). Criteriul de 95% din plan e atins. Link Murderpedia 1.904, link Radford 146, poze 709.
