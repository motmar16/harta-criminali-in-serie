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
