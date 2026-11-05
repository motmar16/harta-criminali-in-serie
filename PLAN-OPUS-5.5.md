# Harta criminalilor în serie — plan de execuție pentru Claude Opus 5.5

Scris pe 5 noiembrie 2026 de Claude Fable 5.1, după verificarea directă a celor cinci surse cerute de Marius.
Acest document este briefing-ul complet: context, decizii luate, decizii deschise, arhitectură, fazele de lucru cu criterii de acceptare și regulile pe care Opus 5.5 trebuie să le respecte. Dacă ceva din plan contrazice ce găsești în realitate (site schimbat, termeni noi, limite de hostare schimbate), notează abaterea în `docs/JURNAL.md` și adaptează, dar nu abandona principiile din secțiunea 3.

---

## 1. Ce vrea Marius

Un site public cu **toți criminalii în serie cunoscuți**, puși pe o **hartă interactivă a lumii** după locația lor. La click pe un criminal apar **locațiile crimelor lui**. Harta trebuie să acopere **toate țările**. Datele vin de pe:

1. https://murderpedia.org/
2. https://maamodt.asp.radford.edu/serial%20killer%20information%20center/project%20description.htm (Radford/FGCU Serial Killer Database)
3. https://killer.cloud/
4. https://serialkillersinfo.com/
5. Wikipedia (și, prin extensie, Wikidata)

Buget: **hostare gratuită, plătește doar domeniul**.

Limbă de lucru cu Marius: română. Limbă implicită a site-ului: engleză (publicul este internațional), cu posibilitate de traducere în română mai târziu. Vezi decizia deschisă D1.

---

## 2. Ce am aflat despre surse (verificat pe 5 nov 2026)

| Sursă | Volum | Formă | Acces tehnic | Licență / termeni | Rol în proiect |
|---|---|---|---|---|---|
| **Wikidata + Wikipedia** | mii de persoane cu ocupația „serial killer" (Q484188); listele Wikipedia „by country" (95 țări + 28 cu criminali neidentificați) și „by number of victims" | structurat (QID, P19 loc naștere, P625 coordonate, P27 cetățenie, P1196, P1399 condamnare etc.) + infobox + text | SPARQL + API MediaWiki, fără restricții, rate limit rezonabil | **CC BY-SA 4.0 / CC0 (Wikidata)**. Reutilizare liberă cu atribuire | **Coloana vertebrală.** Cheia primară a fiecărui criminal este QID-ul Wikidata |
| **Murderpedia** | ~6.900 profiluri (5.852 bărbați, 1.069 femei), index pe ~90 țări + statele SUA | HTML static, câmpuri etichetate: Classification, Characteristics, Number of victims, Date of murder, Date of arrest, Date of birth, Victim profile, Method of murder, Location, Status; apoi narațiune + articole de presă reproduse integral | robots.txt permite tot; fără crawl-delay; charset Windows-1252 (diacriticele apar stricate dacă nu decodezi corect); foldere mixte `a/` și `a1/` | fără notă de copyright pe site, dar **articolele și fotografiile reproduse aparțin publicațiilor originale** | **Sursa principală de îmbogățire factuală.** Extragem **doar câmpurile structurate** (fapte), nu narațiunea, nu fotografiile. Păstrăm URL-ul sursă |
| **Radford/FGCU** | 4.743 criminali (SUA + internațional), pagină actualizată ultima dată în 2016 | bază de date academică, nu există download; doar PDF cu statistici agregate | pe cerere, email la maamodt@radford.edu | nespecificat; uz academic | **Secundar, opțional.** Marius trimite un email de cerere (șablon în Anexa B). Dacă vine, se folosește pentru verificare încrucișată și statistici, **nu se redistribuie brut** |
| **killer.cloud** | 651 profiluri | HTML server-rendered, ~50 câmpuri per profil (locul nașterii ca text, țări active, timeline cu 10 evenimente, întrebări da/nu), **fără coordonate, fără hartă** | robots.txt permite tot, dar **Terms of Service interzic explicit copierea, modificarea și oglindirea materialelor** | restrictiv (copyright, Tennessee) | **NU se scrapuiește.** Se folosește doar ca link extern „vezi și" pe pagina criminalului, cu potrivire manuală/automată după nume. Dacă Marius vrea mai mult, cere permisiunea proprietarului (șablon în Anexa B) |
| **serialkillersinfo.com** | blog WordPress, ~30 articole în categoria „Serial Killers", multe sunt știri | narațiune; un singur tabel de victime per articol, fără infobox | REST API WordPress deschis la `/wp-json/wp/v2/posts` | „All rights reserved" | **Marginal.** Se indexează titlurile prin REST API și se leagă ca „lectură suplimentară" acolo unde numele se potrivește. Nu e bază de date |

Concluzii care dictează arhitectura:

- „Toți criminalii în serie cunoscuți" înseamnă, practic, **uniunea Wikidata ∪ Murderpedia**, deduplicată. Estimare: 7.000–9.000 de persoane. Nicio sursă nu e completă; vom afișa pe site cât de mare e acoperirea și de unde vine fiecare fapt.
- **Locațiile crimelor** nu există nicăieri ca date structurate cu coordonate. Trebuie construite în trei straturi (vezi 5.3): (1) zona de activitate (țară/stat/oraș) din Murderpedia „Location" + infobox Wikipedia; (2) locul nașterii și al morții din Wikidata (au coordonate direct); (3) evenimente per crimă extrase din textul Wikipedia cu un LLM, geocodate, cu grad de încredere afișat.
- Murderpedia are informație excelentă, dar textele reproduse sunt ale altora. **Extragem fapte, nu copiem text.** Faptele nu sunt protejate de copyright; formularea și pozele sunt.

---

## 3. Principii obligatorii (nu se negociază fără Marius)

1. **Fapte, nu text copiat.** Din orice sursă non-liberă se preiau doar date structurate (nume, date, numere, locuri, statut). Biografiile de pe site se scriu din Wikipedia (CC BY-SA, cu atribuire și link la revizie) sau se generează ca rezumat propriu din fapte, niciodată copiate din Murderpedia sau killer.cloud.
2. **Fiecare fapt are sursă.** Modelul de date păstrează `source` + `source_url` + `retrieved_at` per câmp sau per grup de câmpuri. Pagina criminalului afișează sursele.
3. **Crawling politicos.** 1 cerere/secundă per domeniu, User-Agent explicit cu adresă de contact, cache local al HTML-ului brut (în `data/raw/`, **ignorat de git**), reluare din cache la fiecare rerulare. Nu se rulează niciodată crawler-ul complet de două ori în aceeași zi.
4. **Nu se scrapuiește killer.cloud** (ToS). Doar linkuri.
5. **HTML brut nu intră în repo.** În git intră numai datele extrase (`data/*.json`), cache-ul de geocodare și codul.
6. **Prudență juridică și etică.**
   - Se includ persoane **condamnate** sau cazuri **documentate istoric** (în Wikipedia sau Murderpedia). Suspecții neconvicți se marchează explicit „suspected / alleged" și nu li se atribuie crime ca fapt.
   - Numele victimelor se afișează **doar dacă apar deja în Wikipedia**. Altfel: număr, loc, perioadă.
   - Fără fotografii cu victime. Fotografiile criminalilor doar din Wikimedia Commons cu licență verificată (câmpul P18), altfel niciuna.
   - Pagină „Despre / Metodologie / Surse" + avertisment de conținut la prima vizită + formular de corectură (un link mailto sau un issue GitHub).
   - Tonul site-ului: documentar, sobru, fără senzaționalism (fără „top 10 cei mai sângeroși", fără estetică horror).
7. **Zero costuri de hostare.** Dacă o soluție gratuită cere card pentru activare (Cloudflare R2 cere), Marius decide. Implicit se alege varianta fără card.
8. **Totul reproductibil dintr-o comandă.** `make data` (sau `python -m pipeline all`) reface toate datele din cache; `npm run build` face site-ul. Fără pași manuali nedocumentați.

---

## 4. Arhitectură

### 4.1 Vedere de ansamblu

```
[surse web] --crawl/API--> data/raw/ (cache local, gitignored)
                               |
                   pipeline Python (extract, normalize, dedupe, geocode)
                               |
                 data/killers.json  data/events.geojson  data/places.json
                               |
                 site static (Astro + MapLibre GL JS), build la commit
                               |
                 Cloudflare Pages (gratuit) + domeniu propriu
                 basemap: OpenFreeMap (gratuit, fără cheie) sau Protomaps PMTiles
```

Site **complet static**. Fără backend, fără bază de date la runtime. Toate datele sunt fișiere JSON/GeoJSON servite din CDN. Asta elimină costurile și cele mai multe probleme de securitate.

### 4.2 Stack

- **Pipeline de date:** Python 3.12, `httpx`, `beautifulsoup4` + `lxml`, `pydantic` pentru schemă, `rapidfuzz` pentru potrivire de nume, `SPARQLWrapper` sau `httpx` direct pe `query.wikidata.org`, `geopy` doar ca client Nominatim. Teste cu `pytest` pe fixture-uri HTML salvate.
- **Extracție cu LLM** (doar faza 3): Claude API, model Haiku 5.5 pentru volum (text Wikipedia în, JSON de evenimente afară), Sonnet 5.5 pentru cazurile marcate „low confidence" la a doua trecere. Output structurat validat cu pydantic. Consultă skill-ul `claude-api` pentru prețuri actuale înainte de a estima costul; estimarea mea brută este 10–40 USD o singură dată pentru ~8.000 de articole. Marius aprobă bugetul înainte de rulare (D4).
- **Frontend:** Astro (pagini statice pentru SEO: una per criminal, una per țară) + o insulă de hartă în TypeScript cu **MapLibre GL JS**. Clustering nativ MapLibre (`cluster: true`) sau `supercluster` dacă e nevoie de control. Căutare client-side cu `MiniSearch` pe un index JSON precompilat. Fără framework UI greu; CSS propriu sau Tailwind, la alegerea ta.
- **Basemap:** implicit **OpenFreeMap** (stil `liberty` sau `positron`, gratuit, fără cheie, atribuire obligatorie). Rezervă: **Protomaps PMTiles** găzduit pe Cloudflare R2 (10 GB gratuit, fără egress, dar cere card la activare) dacă OpenFreeMap devine indisponibil sau traficul explodează.
- **Hostare:** **Cloudflare Pages** (trafic static nelimitat gratuit, 500 build-uri/lună, 20.000 fișiere/proiect, 25 MiB/fișier). Alternativă echivalentă: GitHub Pages (limită soft 100 GB/lună). Deploy automat din GitHub la push pe `main`.
- **Domeniu:** Cloudflare Registrar (la preț de cost, ~10–12 USD/an pentru .com) sau Porkbun. Marius cumpără; tu doar configurezi DNS-ul în Pages. Vezi D2 pentru nume.
- **Automatizare:** GitHub Actions, workflow lunar care reface datele din Wikidata/Wikipedia (surse libere, rapide) și deschide un PR cu diff-ul; Murderpedia se recrawluiește doar manual, la cerere.

### 4.3 Structura repo-ului

```
harta-criminali-in-serie/
  PLAN-OPUS-5.5.md          # acest fișier
  README.md
  docs/
    JURNAL.md               # jurnal de decizii și abateri de la plan
    METODOLOGIE.md          # devine pagina publică „Methodology"
    SURSE.md                # ce s-a luat de unde, cu ce licență
  pipeline/                 # Python
    sources/
      wikidata.py           # SPARQL: lista + proprietăți + coordonate
      wikipedia.py          # infobox + text articol + liste by country / by victims
      murderpedia.py        # indexuri (litere, țări) + profiluri, câmpuri structurate
      serialkillersinfo.py  # REST API, doar titluri + URL
      killercloud_links.py  # potrivire nume -> URL, fără scraping de conținut
    normalize/
      names.py              # normalizare, transliterare, alias-uri
      dates.py              # „1965 / 1980", „Sep.-Oct. 1996" -> interval ISO
      places.py             # „Alameda County, California, USA" -> ierarhie țară/regiune/localitate
      dedupe.py             # unire Wikidata <-> Murderpedia
    extract/
      events_llm.py         # Claude API: text -> evenimente (crime) structurate
      prompts/
    geocode/
      wikidata_places.py    # întâi coordonate din Wikidata (P625 pe locuri)
      nominatim.py          # apoi Nominatim, 1 req/s, cache persistent
      cache.sqlite          # commit-at (mic, reproductibil)
    build/
      export.py             # -> site/public/data/*.json|geojson
    tests/
      fixtures/             # HTML salvat pentru teste, max câteva pagini
  data/
    raw/                    # gitignored
    killers.json
    events.geojson
    places.json
    coverage.json           # statistici de acoperire afișate pe site
  site/                     # Astro
    src/pages/
      index.astro           # harta
      k/[slug].astro        # pagina criminalului
      country/[code].astro  # pagina țării
      about.astro, methodology.astro, sources.astro
    src/components/Map.ts
    public/data/            # generat de pipeline
  .github/workflows/
    refresh-open-data.yml   # lunar
    deploy.yml              # la push (sau lași Cloudflare Pages să facă build singur)
```

---

## 5. Modelul de date

### 5.1 `Killer` (killers.json, un obiect per persoană)

```json
{
  "id": "Q174398",
  "slug": "andrei-chikatilo",
  "names": {"primary": "Andrei Chikatilo", "aliases": ["The Butcher of Rostov"], "native": "Андрей Чикатило"},
  "sex": "male",
  "birth": {"date": "1936-10-16", "place_id": "P-Q12345", "precision": "day"},
  "death": {"date": "1994-02-14", "place_id": "P-Q67890", "cause": "executed"},
  "countries": ["UA", "RU"],
  "active": {"start": "1978", "end": "1990"},
  "victims": {"proven": 52, "possible": 56, "note": "convicted of 52"},
  "status": "executed",
  "legal_status": "convicted",
  "classification": ["lust killer"],
  "method": ["stabbing", "strangulation"],
  "summary": {"text": "...", "license": "CC BY-SA 4.0", "source_url": "https://en.wikipedia.org/w/index.php?title=...&oldid=..."},
  "image": {"url": "https://commons.wikimedia.org/...", "license": "...", "credit": "..."},
  "links": {"wikipedia": "...", "wikidata": "...", "murderpedia": "...", "killercloud": "...", "serialkillersinfo": null},
  "sources": {"victims": "wikidata", "classification": "murderpedia", "status": "murderpedia"},
  "coverage": {"has_events": true, "event_count": 41, "geocoded_events": 38},
  "retrieved_at": "2026-11-20"
}
```

Reguli:
- `id` este QID Wikidata când există. Dacă persoana există doar în Murderpedia, `id` = `MP-<hash stabil al URL-ului>` și `links.wikidata` = null. Când apare ulterior un QID, se păstrează redirect de la vechiul slug.
- `legal_status` ∈ {convicted, deceased_before_trial, unidentified, suspected, acquitted}. Afișarea diferă pentru `suspected`.
- `victims.proven` e număr sau null; textele gen „0 - 163 +" din Murderpedia se parsează în `{proven, possible, note}` și se păstrează originalul în `note`.

### 5.2 `Place` (places.json)

```json
{"id": "P-Q12345", "name": "Rostov-on-Don", "country": "RU", "admin1": "Rostov Oblast", "lat": 47.23, "lon": 39.72,
 "precision": "city", "geocoder": "wikidata", "geocoded_at": "2026-11-20"}
```

`precision` ∈ {address, city, county, admin1, country}. Pe hartă, punctele cu precizie `country` sau `admin1` se desenează diferit (cerc mai mare, mai transparent) și se jitter-uiesc determinist ca să nu se suprapună 300 de criminali pe centroidul Texasului.

### 5.3 `Event` (events.geojson, un Feature per eveniment)

```json
{"type": "Feature",
 "geometry": {"type": "Point", "coordinates": [39.72, 47.23]},
 "properties": {
   "id": "Q174398-e03", "killer_id": "Q174398",
   "kind": "murder",
   "date": {"start": "1982-06", "end": "1982-06", "precision": "month"},
   "place_id": "P-Q12345",
   "victim_count": 1,
   "victim_label": null,
   "confidence": 0.8,
   "source_url": "https://en.wikipedia.org/w/index.php?title=Andrei_Chikatilo&oldid=...",
   "source_quote": "In June 1982, ... near Rostov",
   "extraction": "llm-haiku-5.5"
 }}
```

`kind` ∈ {murder, attempted, body_found, arrest, birth, death, residence, active_area}. Tipul `active_area` e stratul 1 (zona de activitate), întotdeauna prezent, chiar dacă nu avem evenimente individuale. `victim_label` conține un nume **numai** dacă Wikipedia îl numește.

Cele trei straturi, în ordinea în care se construiesc:
1. **active_area** per criminal: din Murderpedia „Location" + Wikidata/infobox (țară, stat, oraș). Toți criminalii au cel puțin un astfel de punct. Acesta este punctul lor de pe hartă la zoom mic.
2. **birth / death**: direct din Wikidata (P19, P20 au P625 pe item-ul locului). Ieftin, precis.
3. **murder / body_found / arrest** per crimă: extracție LLM din textul articolului Wikipedia (secțiuni „Murders", „Victims", tabele de victime) + cronologia Murderpedia dacă e în câmpuri structurate. Geocodare în două trepte: întâi locul ca item Wikidata (dacă LLM-ul returnează un nume care se rezolvă prin API-ul de căutare Wikidata la un loc cu P625), apoi Nominatim. Fiecare eveniment poartă `confidence` și citatul sursă.

Ce vede utilizatorul la click pe un criminal: punctul principal se evidențiază, apar toate evenimentele lui ca puncte numerotate cronologic, unite cu o linie subțire, iar panoul lateral arată fișa + lista de evenimente cu data, locul, gradul de încredere și linkul la sursă. Dacă nu există evenimente de strat 3, panoul spune clar „Locații individuale ale crimelor nedocumentate în sursele noastre; zona de activitate: X".

---

## 6. Fazele de lucru

Fiecare fază se încheie cu un commit curat, o notă în `docs/JURNAL.md` și un mesaj scurt către Marius cu ce s-a făcut, ce nu, și cifrele de acoperire. Nu treci la faza următoare dacă criteriile de acceptare nu sunt îndeplinite, decât dacă Marius spune explicit.

### Faza 0 — Schelet (0,5 zi)
- Inițializezi repo-ul git în `C:\Users\Marius\Desktop\PROECTE\harta-criminali-in-serie`, structura din 4.3, `.gitignore` cu `data/raw/`, `pyproject.toml`, `site/` cu Astro + MapLibre și o hartă goală pe OpenFreeMap.
- Un `README.md` scurt și `docs/JURNAL.md` cu prima intrare.
- **Acceptare:** `npm run dev` arată harta lumii; `python -m pipeline --help` răspunde.

### Faza 1 — Coloana vertebrală: Wikidata + Wikipedia (2–3 zile)
- SPARQL: toate item-urile umane cu P106 = Q484188 sau P31/P279* ⊂ Q484188, plus P21, P569/P570, P19/P20 (cu P625 ale locurilor), P27, P1196, P18, P1399, sitelink enwiki. Paginat, cu retry. Înregistrezi numărul obținut în `coverage.json`.
- Wikipedia: pentru fiecare sitelink, infobox-ul (câmpurile `victims`, `country`, `states`, `beginyear`/`endyear`, `apprehended`, `conviction_status`) și textul articolului (wikitext sau HTML parsat), salvat în `data/raw/wikipedia/`. În plus, listele „by country", „by number of victims", „before 1900" ca verificare: orice nume din liste care nu are QID cu P106 potrivit se adaugă cu `source: wikipedia-list`.
- Stratul 1 (`active_area`) și stratul 2 (`birth`/`death`) construite; export către site.
- Harta afișează toți criminalii, clusterizați; click deschide panoul cu fișa minimă și linkurile.
- **Acceptare:** ≥ 95% din criminali au cel puțin un punct `active_area` geocodat la nivel ≤ admin1; pagina `/country/XX` există pentru fiecare țară cu ≥ 1 criminal; raport de acoperire publicat în `coverage.json`.

### Faza 2 — Îmbogățire din Murderpedia (2–3 zile)
- Crawler: indexurile pe litere (bărbați A–Z, femei A–Z) + indexul pe țări; apoi profilurile. Decodare Windows-1252. Cache strict. ~7.000 de pagini la 1 req/s ≈ 2 ore; rulezi o singură dată, în fundal.
- Extragi **doar** câmpurile etichetate (Classification, Characteristics, Number of victims, Date of murder, Date of arrest, Date of birth, Victim profile, Method of murder, Location, Status) + numele + URL + indicator că există galerie foto (nu descarci pozele).
- Deduplicare cu Wikidata: potrivire după nume normalizat + an naștere ± 1 + țară; `rapidfuzz` cu prag conservator; cazurile ambigue merg într-un CSV `data/validare/dedupe_ambigue.csv` pe care Marius îl poate corecta manual (coloană `decizie`). Fără QID → `MP-` id.
- Precedență per câmp documentată în `docs/METODOLOGIE.md` (ex. victime: Wikidata dacă există, altfel Murderpedia; clasificare și metodă: Murderpedia; statut: cel mai recent).
- **Acceptare:** ≥ 6.500 de profiluri Murderpedia parsate fără eroare; rata de potrivire cu Wikidata raportată; ≤ 2% ambigue nerezolvate automat; niciun text narativ Murderpedia în repo.

### Faza 3 — Locațiile crimelor (3–5 zile, plus timp de rulare)
- Pentru fiecare criminal cu articol Wikipedia: trimiți la Claude (Haiku 5.5) secțiunile relevante + un prompt care cere o listă de evenimente în schema 5.3, cu citat-sursă obligatoriu pentru fiecare, fără inventare („dacă locul nu e în text, omite evenimentul"). Validezi cu pydantic; respingi evenimentele al căror citat nu se regăsește literal în text.
- Geocodare: Wikidata search → Nominatim, cache SQLite commit-at. Respectă politica Nominatim (1 req/s, User-Agent cu email, fără bulk peste ce e rezonabil; dacă volumul depășește ~20.000 de locuri unice, rulezi pe mai multe zile sau instalezi Photon local).
- A doua trecere cu Sonnet 5.5 doar pe cazurile cu `confidence < 0.6` sau cu > 20 de evenimente.
- Eșantion de validare: 50 de criminali aleși aleator, verificați manual (tu, apoi Marius pe 10 dintre ei); raportezi precizia.
- UI: la click, evenimentele numerotate, linia cronologică, panoul cu surse; slider de timp opțional (D5).
- **Acceptare:** ≥ 60% din criminalii cu articol Wikipedia au ≥ 1 eveniment de strat 3 geocodat; precizie ≥ 90% pe eșantion; costul API raportat; nicio victimă numită fără să fie în Wikipedia.

### Faza 4 — Site complet (2–3 zile)
- Pagini: hartă (index), `/k/[slug]`, `/country/[code]`, about, methodology, sources, content warning la prima vizită (localStorage), formular de corecturi (mailto + link către issues).
- Căutare (MiniSearch), filtre: țară, perioadă, număr victime, sex, statut, strat de date disponibil. Starea hărții și filtrele în URL (`?c=RU&from=1970`), ca linkurile să fie partajabile.
- Performanță: `killers.json` împărțit în index (nume, slug, punct principal, țară, victime; sub 1 MB gzip) + fișiere per criminal încărcate la click. Lighthouse ≥ 90 pe mobil la Performance și Accessibility.
- SEO: titluri, meta description, `schema.org/Person` + `Place`, sitemap, OpenGraph cu o imagine statică a hărții per țară. Folosește skill-urile `seo` și `accessibility` din sesiune.
- Design: sobru, documentar, temă întunecată implicită cu hartă dezaturată, fără roșu-sânge, fără fonturi „horror". Citește skill-ul `frontend-design`. Atribuire vizibilă: OpenStreetMap, OpenFreeMap/Protomaps, Wikipedia (CC BY-SA), Murderpedia (ca sursă de fapte).
- **Acceptare:** build static fără erori; toate paginile sub 20.000 de fișiere (limita Cloudflare Pages; dacă depășești, generezi paginile criminalilor pe client dintr-un singur JSON și păstrezi statice doar țările); mobil utilizabil; `methodology` descrie exact precedența și limitele.

### Faza 5 — Publicare (0,5–1 zi)
- Repo pe GitHub (public sau privat, D3). Cloudflare Pages conectat la repo, build `cd site && npm ci && npm run build`, output `site/dist`.
- Marius cumpără domeniul; tu dai instrucțiunile DNS (CNAME către `<proiect>.pages.dev`, sau nameservere Cloudflare dacă domeniul e la Cloudflare Registrar).
- Workflow lunar `refresh-open-data.yml`: reface faza 1 (Wikidata/Wikipedia) și deschide PR cu diff-ul de acoperire. Murderpedia și faza 3 nu rulează automat.
- Pagina de stare `coverage.json` afișată în footer: „N criminali, M evenimente, actualizat la data X".
- **Acceptare:** site live pe domeniu, HTTPS, deploy la push, fără niciun cost lunar.

### Faza 6 — Opțional, după lansare
- Email către Radford (Anexa B). Dacă vin datele: verificare încrucișată a numerelor de victime și a perioadelor; statistici agregate pe pagina țării, cu citare obligatorie a bazei de date.
- Email către killer.cloud pentru permisiune de a prelua câmpurile structurate. Până la răspuns, doar link.
- Traducere RO a interfeței (nu a biografiilor).
- Import de liste suplimentare Wikipedia pe țări (Brazilia, Chile, China, Columbia, Cehia, Franța, Germania, Japonia au liste proprii).

---

## 7. Decizii deschise pentru Marius

Opus 5.5 pune aceste întrebări **o singură dată, la început**, și merge cu implicitul dacă nu primește răspuns:

- **D1. Limba site-ului.** Implicit: engleză, UI pregătită pentru i18n, română ulterior.
- **D2. Numele domeniului.** Nu e nevoie pentru dezvoltare; se cumpără la faza 5. Sugestie: ceva neutru, documentar (evită cuvinte-cheie senzaționaliste).
- **D3. Repo public sau privat.** Implicit: public (codul și datele extrase din surse libere; cache-ul brut nu e în repo oricum). Public ajută și la corecturi prin issues.
- **D4. Bugetul Claude API pentru faza 3.** Implicit: nu se rulează până nu aprobă Marius o sumă; se rulează întâi pe 100 de criminali și se raportează costul real extrapolat.
- **D5. Slider de timp** (animație a crimelor pe decenii). Implicit: da, dacă bugetul de timp al fazei 4 permite; altfel faza 6.
- **D6. Card la Cloudflare pentru R2** (doar dacă OpenFreeMap nu merge). Implicit: nu.

---

## 8. Riscuri și cum le tratezi

| Risc | Probabilitate | Tratament |
|---|---|---|
| Murderpedia blochează sau cade în timpul crawl-ului | medie | cache incremental, reluare; dacă persistă, continui cu ce ai și notezi în jurnal |
| LLM inventează locuri/evenimente | sigură fără contramăsuri | citat obligatoriu verificat literal în text; `confidence`; eșantion validat manual; buton „raportează eroare" |
| Suprapunere pe hartă (sute de puncte pe același centroid) | sigură | clustering + jitter determinist + marcaj de precizie |
| Plângere a unei persoane menționate / rudă a victimei | mică, dar gravă | politică de includere (doar condamnați/istorici), fără nume de victime în afara Wikipedia, canal de corectură, răspuns rapid de eliminare la cerere documentată |
| Trafic viral peste limitele gratuite | mică | Cloudflare Pages n-are limită de trafic static; basemap-ul e singurul punct sensibil, de aceea există rezerva Protomaps |
| Depășire 20.000 de fișiere pe Cloudflare Pages | medie la ~8.000 de criminali × pagini | pagină per criminal randată pe client din JSON; statice doar țările și paginile fixe |
| Reconstruirea completă durează ore | medie | cache-ul brut e sursa de adevăr; `make data` reface doar din cache în minute |

---

## 9. Cum raportezi lui Marius

- Scurt, în română, la finalul fiecărei faze: ce e gata, cifrele de acoperire, ce ai lăsat deoparte și de ce, ce decizie îi aparține.
- Nu-i trimite loguri; trimite-i linkul către `coverage.json` sau către pagina de preview Cloudflare.
- Când ceva din plan se dovedește greșit (număr, licență, limită), spune-o direct și notează în `docs/JURNAL.md`.

---

## Anexa A — Interogări și comenzi de pornire

SPARQL de bază (verifică și ajustează; Q484188 = serial killer, Q5 = human):

```sparql
SELECT ?p ?pLabel ?sex ?dob ?dod ?pob ?pobCoord ?pod ?podCoord ?citizenship ?article WHERE {
  { ?p wdt:P106 wd:Q484188 } UNION { ?p wdt:P31/wdt:P279* wd:Q484188 }
  ?p wdt:P31 wd:Q5 .
  OPTIONAL { ?p wdt:P21 ?sex }
  OPTIONAL { ?p wdt:P569 ?dob }
  OPTIONAL { ?p wdt:P570 ?dod }
  OPTIONAL { ?p wdt:P19 ?pob . OPTIONAL { ?pob wdt:P625 ?pobCoord } }
  OPTIONAL { ?p wdt:P20 ?pod . OPTIONAL { ?pod wdt:P625 ?podCoord } }
  OPTIONAL { ?p wdt:P27 ?citizenship }
  OPTIONAL { ?article schema:about ?p ; schema:isPartOf <https://en.wikipedia.org/> }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
```

Rulează-l paginat (`LIMIT 2000 OFFSET n`) sau împărțit pe litera inițială dacă expiră. Notează numărul total în `coverage.json` și în jurnal.

Murderpedia, puncte de intrare:
- `https://murderpedia.org/male.A/index.A.htm` … `male.Z`, `https://murderpedia.org/female.A/index.A.htm` … `female.Z`
- `https://murderpedia.org/index-by-country.htm`, `https://murderpedia.org/index-by-country-female.htm`
- Decodează răspunsul ca `cp1252`, nu `utf-8`. Linkurile sunt relative, folderele variază (`a/`, `a1/`).

serialkillersinfo, doar titluri: `https://serialkillersinfo.com/wp-json/wp/v2/posts?per_page=100&_fields=id,slug,title,link,date`.

Nominatim: `User-Agent: harta-criminali-in-serie/0.1 (contact: <email Marius>)`, max 1 req/s, cache obligatoriu, fără reîncercări agresive.

## Anexa B — Șabloane de email (le trimite Marius)

**Către Radford (maamodt@radford.edu):**
> Subject: Request for access to the Radford/FGCU Serial Killer Database
> Dear Dr. Aamodt, I am building a non-commercial, open educational website that maps documented serial killers worldwide, with sources cited per record. I would like to ask whether the Radford/FGCU Serial Killer Database can be shared for cross-checking victim counts and active periods, and under what citation and usage terms. The raw database would not be redistributed; only aggregate statistics with full attribution. Thank you, Marius Moțoi.

**Către killer.cloud (contact de pe site):**
> Subject: Permission to reference structured fields from Killer.Cloud
> Hello, I run a non-commercial educational mapping project on documented serial killers. Your Terms of Service restrict copying, so I am currently only linking to your profiles. Would you allow the reuse of a limited set of structured fields (victims count, years active, countries) with attribution and a link back to each profile? Thank you, Marius Moțoi.

## Anexa C — Ce am verificat eu și ce nu

Verificat pe 5 nov 2026 prin fetch direct: robots.txt și structura pentru murderpedia.org, killer.cloud (inclusiv Terms of Service), serialkillersinfo.com (inclusiv REST API), pagina de descriere Radford, cele două liste Wikipedia. Limitele Cloudflare Pages și opțiunile OpenFreeMap/Protomaps sunt din surse secundare din 2026; confirmă-le pe paginile oficiale înainte de faza 5.

Neverificat: numărul exact de item-uri Wikidata (rulează interogarea), conținutul PDF-ului de statistici Radford, paginile de privacy/terms ale Murderpedia și serialkillersinfo, prețul curent al domeniilor.
