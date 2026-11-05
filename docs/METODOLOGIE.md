# Metodologie

Document de lucru; devine pagina publică „Methodology” în faza 4.

## Cine e inclus (faza 1)

Persoanele umane (P31 = Q5) din Wikidata cu ocupația „serial killer” (P106 = Q484188) sau instanță a unei subclase a lui Q484188,
plus persoanele umane legate din listele Wikipedia „List of serial killers by country”, „… by number of victims” și
„… before 1900” care nu au ocupația setată în Wikidata (marcate `wikipedia-list`).

## Statut juridic (`legal_status`)

Derivat conservator; când nu se poate stabili, rămâne `null` și site-ul afișează „statut neverificat”:
- `convicted`: Wikidata P1399 (convicted of) sau infobox cu `conviction`/`criminal_penalty`/`penalty`.
- `unidentified`: categoria Wikipedia „Unidentified serial killers”.
- `suspected`: categorie Wikipedia cu „Suspected serial killers” / „alleged”, fără condamnare. Nu li se atribuie crime ca fapt.
- `acquitted`: categorie „People acquitted of …”, fără condamnare.

## Zona de activitate (stratul 1, `active_area`)

În ordinea preferinței, primul strat care dă cel puțin un loc rezolvat:
1. infobox Wikipedia engleză: `locations`, `location`, `cities`, `city`, `states`, `state`, `region`, `country`, `countries`;
2. linkurile geografice din introducerea articolului (engleză, apoi alte limbi);
3. ca rezervă, țara (P17) a locului morții sau cetățenia (P27) — doar la nivel de țară.

Fiecare loc e rezolvat prin Wikidata (titlu articol -> item -> P625 coordonate, P17 țară).
Precizia vine din clasa item-ului: așezare umană = `city`, subdiviziune de nivel 2 = `county`, de nivel 1 = `admin1`, stat = `country`.
Punctele `admin1`/`country` se desenează mai mare și transparent și se decalează determinist (jitter) ca să nu se suprapună.

## Naștere și moarte (stratul 2)

Direct din Wikidata: P19/P20 cu P625 pe item-ul locului.

## Victime

Wikidata P1345 când există, altfel câmpul `victims` din infobox; textul original rămâne în `victims.note`.
