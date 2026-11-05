# Metodologie

Document de lucru; devine pagina publică „Methodology” în faza 4.

## Cine e inclus (faza 1)

- Persoanele umane (P31 = Q5) din Wikidata cu ocupația „serial killer” (P106 = Q484188) sau instanță a unei subclase
  a lui Q484188. Personajele fictive și grupurile (duo-uri, bande) nu sunt incluse.
- Plus persoanele umane legate (primul link al fiecărei intrări) din listele Wikipedia „List of serial killers by
  country” (inclusiv sub-listele spre care trimite prin {{Main}}: SUA, Regatul Unit, Africa de Sud, Columbia, China,
  Chile), „… by number of victims” și „… before 1900”, care nu au ocupația setată în Wikidata (`inclusion: wikipedia-list`).
  Intrările care duc la articole despre cazuri (nu persoane) sunt ignorate în faza 1.

## Statut juridic (`legal_status`)

Derivat conservator; când nu se poate stabili, rămâne `null` și site-ul afișează „statut neverificat”:
- `convicted`: Wikidata P1399 (convicted of) sau infobox cu `conviction`/`criminal_penalty`/`penalty`.
- `unidentified`: categoria Wikipedia „Unidentified serial killers”.
- `suspected`: categorie Wikipedia cu „Suspected serial killers” / „alleged”, fără condamnare, sau persoană care apare
  în liste doar la secțiuni „Disputed / Unconfirmed / Suspected / Unidentified”. Nu li se atribuie crime ca fapt.
- `deceased_before_trial`: categorie „… died before trial”.
- `acquitted`: categorie „People acquitted of …”, fără condamnare.

## Zona de activitate (stratul 1, `active_area`)

Se ia primul nivel care dă cel puțin un loc rezolvat:
1. **infobox Wikipedia engleză**, câmpurile fine `locations`, `location`, `cities`, `city`, `states`, `state`, `region`
   (încredere 0,9). Locurile la nivel de țară din aceste câmpuri se ignoră (ex. „Georgia” într-o listă de state SUA
   s-ar rezolva greșit la țara Georgia).
2. **linkurile geografice din introducerea articolului** (engleză, altfel prima limbă disponibilă), fără ce e
   între paranteze, unde multe Wikipedii pun locul nașterii/morții (încredere 0,6).
3. **linkurile din secțiunile despre crime** ale articolului englez (titluri cu „Murders”, „Crimes”, „Victims”,
   „Killings”, „Investigation” etc.), apoi din **restul corpului**, excluzând secțiunile de biografie
   („Early life”, „Personal life”), proces, închisoare, moarte și media. Se păstrează cele mai des menționate
   maximum 5 locuri (încredere 0,5, respectiv 0,4).
4. **doar nivel de țară**, în ordine: câmpul `country` din infobox, țările legate în introducere, țara din lista
   Wikipedia în care apare persoana (secțiunea „by country” = țara unde au avut loc majoritatea crimelor),
   cetățenia din Wikidata (P27, aproximare) — încredere 0,3.

Dacă infobox-ul are câmpul `country`, locurile fine dintr-o altă țară se elimină (protecție la omonime).
Maxim 15 puncte de zonă per persoană. Primul punct e punctul persoanei pe harta de ansamblu.

Fiecare loc e rezolvat prin Wikidata (titlu articol -> item -> P625 coordonate, P17 țară cu cod ISO).
Precizia vine din clasa item-ului (P31/P279*): clădire/structură = `address`; așezare umană sau municipiu = `city`;
subdiviziune de nivel 2–3 = `county`; subdiviziune de nivel 1, entitate administrativă de nivel necunoscut sau
regiune geografică = `admin1`; stat = `country`. Organizațiile prinse doar ca „regiune” sunt ignorate.
Încrederea (`confidence`) descrie sursa locului, nu e o probabilitate calibrată.
Punctele `admin1`/`country` se desenează mai mare și mai transparent și se decalează determinist (jitter,
după ID-ul evenimentului) ca să nu se suprapună pe centroid. Coordonatele nedecalate sunt în `places.json`.

## Naștere și moarte (stratul 2)

Direct din Wikidata: P19/P20 cu P625 pe item-ul locului.

## Victime

Wikidata P1345 când există, altfel câmpul `victims` din infobox; textul original rămâne în `victims.note`.

## Murderpedia (faza 2)

Din fiecare profil se extrag **doar** câmpurile etichetate: Classification, Characteristics, Number of victims,
Date of murder, Date of arrest, Date of birth, Victim profile, Method of murder, Location, Status, plus numele,
URL-ul și un indicator că există galerie foto. Narațiunea, articolele de presă și fotografiile nu se preiau.

- **Cine intră ca persoană nouă:** doar profilurile cu „Serial killer” în Classification (cele cu „?” devin
  `suspected`). Celelalte profiluri (omoruri simple, crime în masă) servesc doar la îmbogățirea persoanelor deja
  existente, și numai cu potrivire strictă (același an de naștere).
- **Deduplicare:** nume normalizat (rapidfuzz) + an naștere ± 1 + țară. Cazurile neclare merg în
  `data/validare/dedupe_ambigue.csv`; o decizie scrisă în coloana `decizie` (QID, „nou” sau „diferit”) e respectată
  la rularea următoare.
- **„Victim profile” nu se publică** (poate conține nume de victime care nu apar în Wikipedia). Din el se derivă doar
  etichete de tip: femei, bărbați, copii (toate vârstele < 16), vârstnici (toate ≥ 65), familie, pacienți etc.
- **Locația** („Yonkers, Westchester County, New York, USA”) se rezolvă tot prin Wikipedia/Wikidata, încercând titluri
  de la specific la general („Yonkers, New York”, „Yonkers”, „Westchester County, New York”…), cu verificarea țării.

Precedență per câmp:
| Câmp | Ordine |
|---|---|
| victime | Wikidata P1345 → infobox Wikipedia → Murderpedia |
| perioadă activă | infobox Wikipedia → anii din „Date of murder” (Murderpedia) |
| zonă de activitate | Wikipedia dacă e la nivel ≤ admin1; altfel Murderpedia „Location”; altfel țara |
| clasificare | Murderpedia |
| metodă, tip victime | reuniunea etichetelor din Wikipedia și Murderpedia |
| statut juridic | Wikidata/Wikipedia; dacă lipsește, din „Status” (Murderpedia) |

## Imagini

Doar Wikimedia Commons, prin P18 din Wikidata, cu licența citită din metadatele fișierului (domeniu public, CC0,
CC BY, CC BY-SA, FAL, OGL, GFDL). Nu se afișează imagini pentru autori neidentificați și nici fișiere al căror nume
sugerează victime sau locul crimei. Fiecare imagine are autorul și licența afișate sub ea.

## Etichete pentru filtre

Metoda (împușcare, înjunghiere, strangulare, otrăvire, lovire, sufocare, incendiere, înec) și tipul victimelor se obțin
din cuvinte-cheie, deci sunt incomplete și pot avea erori; site-ul o spune explicit lângă filtre.

## Radford/FGCU

Baza Radford/FGCU nu are pagini publice per persoană; site-ul pune doar un link general către descrierea proiectului.
Datele pot fi cerute prin email (șablon în PLAN, Anexa B) și, dacă vin, se folosesc doar pentru verificare și statistici.
