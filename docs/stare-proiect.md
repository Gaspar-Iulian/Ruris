# Starea proiectului și planul de livrare

Data evaluării: 21 octombrie 2026.

Acest document separă funcțiile implementate de lucrările propuse. Pachetul
pentru excepțiile de la recepție este implementat și verificat; lucrările ulterioare
sunt enumerate separat.

## 1. Obiectivul aplicației

Achizițiile, Depozitul și Contabilitatea folosesc aceleași documente și cantități,
cu permisiuni diferite. O factură poate fi aprobată numai când este acoperită de
marfă acceptată și corespunde condițiilor comenzii. Întârzierile și blocajele
trebuie să ajungă la persoanele responsabile, iar operațiile să poată fi urmărite.

Tehnologii folosite: Python, Flask, SQLAlchemy, PostgreSQL, React, bcrypt și JWT.
Docker pornește momentan PostgreSQL și Mailpit, serviciul local pentru testarea emailurilor.

## 2. Ce avem implementat

| Zonă | Ce funcționează acum |
| --- | --- |
| Autentificare | Login, logout, parole cu bcrypt, JWT în cookie HttpOnly, protecție CSRF și verificarea sesiunii în backend. |
| Roluri și conturi | Administratorul creează conturi pentru Achiziții, Depozit și Contabilitate. Accesul este verificat în API; meniurile reflectă rolul. Administratorul nu primește automat permisiunile operaționale ale echipelor. |
| Catalog | Achizițiile pot crea furnizori și produse, cu validări pentru identitate, cod și unitate de măsură. |
| Comenzi | Creare și confirmare cu produse, cantități, prețuri, TVA, monedă și termen. Lista afișează furnizorul și produsele reale, cantitatea și unitatea; prețurile sunt afișate rolurilor autorizate. |
| Livrare | Cantitățile acceptate din recepțiile confirmate determină livrarea: neprimită, parțială sau completă. Restul este calculat pentru fiecare produs. |
| Recepții | Mai multe recepții pentru aceeași comandă, sosiri fără comandă, inclusiv produse neidentificate. Cantitățile în așteptare se acceptă sau se resping ulterior, inclusiv parțial. Numai cantitatea acceptată intră în stoc. |
| Clarificări | Pagină comună celor trei echipe și contor pe prima pagină. Achizițiile asociază o comandă compatibilă; Depozitul acceptă sau respinge; Contabilitatea consultă rezultatul și reia verificarea facturii. |
| Stoc | Mișcări de intrare și solduri calculate din cantitățile acceptate. |
| Facturi | Factură pornită din comandă sau introdusă manual, în RON/EUR. Asociere la recepții, verificare, aprobare și înregistrarea plății sunt operații distincte. |
| Diferențe și asocieri | Cantitățile lipsă și diferențele de preț, TVA, monedă sau unitate sunt evidențiate. Cantitatea deja asociată unei facturi nu poate fi folosită din nou. |
| Corectarea facturilor | O factură poate fi corectată înainte de aprobare, după eliberarea asocierilor active. Schimbările invalidează verificarea anterioară. |
| Curs valutar | Curs istoric BNR preluat automat la verificarea facturii, cu sursa și conversia păstrate. Calculele monetare folosesc Decimal. |
| Audit | Operațiile importante păstrează actorul, momentul, motivul și schimbările. Auditul este atomic și protejat împotriva modificării sau ștergerii. Istoricul recepției este vizibil în portal, inclusiv comenzile și cantitățile deciziilor ulterioare. |
| Notificări | Există worker zilnic, emailuri pentru comenzi întârziate și facturi blocate, jurnal, deduplicare și reîncercări. Trimiterea este configurată momentan către Mailpit local. |
| Interfață | Portal în română, culori RURIS, pagini pe rol, formulare și detalii, paginare și căutare în pagina curentă. |

Starea comercială a comenzii și starea livrării sunt separate. O comandă poate
rămâne „Confirmată”, având livrarea „Completă” după recepțiile 77 + 23 din 100.

Înregistrarea plății păstrează referința și momentul plății. Aplicația nu execută
transferuri bancare.

### Cum funcționează acum asocierea facturii

1. Contabilitatea introduce factura și verifică sursele disponibile.
2. „Propune asocierea” completează cantitățile în formular, fără salvare.
3. „Salvează asocierile” rezervă cantitățile acceptate pentru factură.
4. „Asociază și verifică” poate efectua consecutiv salvarea și verificarea;
   simpla disponibilitate a mărfii nu reprezintă o asociere deja salvată.
5. Verificarea produce blocaje explicite sau starea „Verificată”.
6. Aprobarea repetă controalele. Plata se înregistrează separat, după aprobare.

O asociere poate fi eliberată cu motiv înainte de aprobare. Facturile aprobate
și plătite nu se modifică prin fluxul obișnuit. Un conflict sau un rezultat de
rețea incert cere actualizarea datelor înaintea unei alte operații.

## 3. Ce mai trebuie în raport cu cerințele

| Cerință sau limită | Starea actuală | Lucrarea rămasă |
| --- | --- | --- |
| Marfă sosită fără comandă | Implementate sosirea, confirmarea în așteptare, asocierea comercială și decizia ulterioară. | Furnizorul trebuie să existe în catalog; dacă lipsește, Achizițiile îl adaugă mai întâi. |
| Cantități în așteptare | Implementate acceptarea și respingerea parțială, cu efect asupra stocului, livrării și cantității eligibile pentru facturi. | Corecțiile unor decizii deja definitive rămân un flux separat, viitor. |
| Trasabilitate accesibilă echipelor | Auditul există în baza de date, iar recepțiile au istoric vizibil, cu acces limitat la documentele permise. | Extinderea istoricului vizibil la comenzi, facturi și administrare. |
| Emailuri periodice utilizabile la livrare | Logica există; Mailpit este local, workerul nu rulează permanent. | SMTP configurabil, pornire permanentă și verificarea destinatarilor, programării și reîncercărilor. Clarificările trebuie direcționate către echipa responsabilă. |
| Curs în ziua facturii | Este folosită strict data facturii. Lipsa cursului publicat produce blocaj. | Explicarea în interfață și documentație a acestei situații și testarea scenariilor EUR. Orice regulă alternativă pentru zile fără curs trebuie decisă explicit. |
| Stoc complet | Sunt implementate intrările din recepții acceptate. | Pentru un depozit cu consum și retururi: ieșiri, retururi și ajustări documentate. Până atunci, soldul reflectă numai intrările înregistrate. |
| Portabilitate pe alt PC | Docker pentru baza de date și Mailpit; backendul și frontendul pornesc separat. | Containere pentru backend, frontend și worker, configurare de mediu și verificarea pornirii de la zero. |
| Livrare în Git | Repository configurat și checkpointuri publicate anterior; există lucrări ulterioare în spațiul local. | Checkpoint final și push numai la cererea utilizatorului, apoi verificarea instrucțiunilor de pornire. |

### Completări utile, distincte de cerințele explicite

- Introducerea totalurilor declarate de furnizor, pentru a le compara cu sumele
  calculate din poziții; acum totalurile sunt calculate din valorile introduse.
- Atașarea facturii și a documentelor justificative.
- Administrarea completă a conturilor și catalogului din interfață.
- Închiderea justificată a resturilor din comenzi și corecții documentate după
  confirmare sau plată, cu reguli pentru efectele ulterioare.
- Catalog de oferte produs–furnizor. Acum legătura comercială este în comandă;
  nu există încă o listă de oferte a furnizorilor.

OCR, integrarea bancară, plățile parțiale și mai multe depozite pot rămâne în
afara versiunii pentru interviu. Nu sunt necesare pentru demonstrarea fluxului cerut.

## 4. Ce am verificat deja

Scenarii parcurse prin browser, Flask și PostgreSQL reale, cu date izolate:

| Scenariu | Rezultat verificat |
| --- | --- |
| 100 comandate, recepții 77 + 23, factură 100 | Asociere la ambele recepții, verificare, aprobare, înregistrarea plății, stoc 100, livrare completă și fără întârziere. |
| 100 facturate, numai 77 acceptate | Factură blocată, fără aprobare sau plată; rest 23 la întârzieri. |
| Preț facturat 3, preț comandat 2 | Diferența este vizibilă și blochează verificarea; corectarea la 2 și asocierea permit verificarea. |
| Două facturi pentru aceeași marfă | A doua nu poate consuma cantitatea rezervată primei; eliberarea primei asocieri o face din nou disponibilă. |
| Factură de 5 M2, blocată, cu 5 M2 acceptați disponibili | „Asociază și verifică”, cu observații, salvează asocierea și produce starea „Verificată”. |
| Sosire fără comandă, produs neidentificat, 10 bucăți | Stoc inițial 0, factură blocată; Achizițiile identifică sursa, Depozitul acceptă 6 și respinge 4, stocul devine 6. Asocierea și reverificarea permit verificarea și aprobarea facturii de 6. Istoricul și afișarea pe mobil sunt verificate. |
| 14 sosite pentru o comandă de 10, apoi comandă suplimentară de 4 | Primele 10 rămân pe comanda inițială; cele 4 sunt acceptate separat pe comanda suplimentară. Ambele livrări sunt complete, stocul este 14 și fiecare factură folosește sursa proprie. |

Aceste scenarii complete au folosit facturi în RON. Nu reprezintă o demonstrație
completă a livrării prin SMTP extern sau a tuturor situațiilor de curs EUR.

Testele reale folosesc o schemă PostgreSQL temporară și o tranzacție exterioară;
la final sunt anulate datele și schema. Testele nu efectuează plăți bancare.
Testele de interfață cu răspunsuri simulate sunt separate de aceste scenarii reale.

La verificarea extinsă a acestui pachet au trecut 250 de teste backend pentru
recepții, concurență, livrare, asocieri și verificarea facturilor. După completarea
istoricului și a cazurilor de protecție au trecut 168 de teste pentru recepții și
excepții. Aceste selecții se suprapun și nu se însumează.

Au trecut 103 teste de interfață cu răspunsuri simulate și toate cele 7 scenarii
complete cu API real. Au fost verificate și blocarea repetării unei operații,
conflictele de versiune și păstrarea datelor când auditul eșuează. După protecția
suplimentară pentru schimbarea modului de recepție au trecut 31 de teste de
interfață relevante și buildul final. Și aceste selecții se suprapun.

Migrarea `0021_receipt_exceptions` este aplicată în baza locală. Verificarea
migrărilor nu a identificat diferențe față de modele. Numărul documentelor și
mișcările de stoc existente au rămas neschimbate după migrare.

## 5. Pachet implementat: excepțiile de la recepție

### Rezultatul livrat

Marfa sosită fără comandă și cantitățile în așteptare pot fi urmărite de la
sosire până la decizia de acceptare sau respingere. Istoricul este păstrat, iar
stocul și eligibilitatea pentru facturare cresc numai prin acceptare.

### Ce poate face fiecare echipă

| Echipă | Funcții implementate |
| --- | --- |
| Depozit | Înregistrează sosirea cu sau fără comandă, vede pozițiile în așteptare și înregistrează decizii parțiale de acceptare sau respingere. |
| Achiziții | Vede clarificările care îi revin, identifică produsul și acoperirea comercială, asociază o comandă confirmată compatibilă sau pregătește una nouă. |
| Contabilitate | Vede ce cantitate este acceptată și disponibilă pentru asociere și poate reverifica factura după rezolvare. |
| Utilizatori autorizați | Văd istoricul documentului: cine a înregistrat sosirea, cine a clarificat, cine a decis, când, de ce și pentru ce cantitate. |

### Reguli implementate în cod

1. Sosirea fizică nu înseamnă automat stoc disponibil. Marfa fără comandă rămâne
   în așteptare până la clarificare.
2. Un produs încă necunoscut în catalog poate fi descris la sosire; intrarea în
   stoc cere identificarea produsului și a unității de măsură.
3. Acceptarea cere o comandă confirmată compatibilă și cantitate rămasă disponibilă.
   Achizițiile clarifică acoperirea comercială; Depozitul decide acceptarea fizică.
4. Cantitatea sosită și deciziile anterioare se păstrează. O decizie nouă consumă
   numai din cantitatea încă în așteptare: acceptat + respins + în așteptare = sosit.
5. Un surplus acoperit ulterior prin altă comandă păstrează separat sursa noii
   acceptări. Cantitățile deja acceptate nu sunt mutate retroactiv pe altă comandă.
6. Cantitățile respinse sau în așteptare nu intră în stoc și nu justifică factura.
7. Decizia, mișcarea de stoc și auditul sunt salvate într-o singură tranzacție.
   Versiunile și blocarea în baza de date previn aplicarea aceleiași decizii de două ori.
8. Rezolvarea recepției nu aprobă automat o factură. Contabilitatea asociază
   cantitatea eligibilă și reia verificarea.

### Cum testezi din portal

1. **Depozit → Recepție nouă → Fără comandă:** selectează furnizorul, documentul,
   momentul sosirii și 10 bucăți. Poți alege „Produs neidentificat” și scrie descrierea.
2. Salvează ciorna, deschide detaliile și confirmă toate cele 10 în așteptare.
3. **Achiziții:** creează și confirmă o comandă compatibilă dacă nu există deja;
   apoi, în **Clarificări**, deschide recepția și asociază poziția comenzii, cu observații.
4. **Depozit → Clarificări:** acceptă 6 bucăți, cu observații; ulterior respinge
   celelalte 4. Verifică stocul, restul de livrat și istoricul recepției.
5. **Contabilitate:** o factură de 6 bucăți poate fi asociată și verificată;
   o factură de 10 rămâne neacoperită pentru 4 bucăți.

Pentru o recepție obișnuită care are deja o comandă compatibilă și rest de livrat,
Depozitul poate accepta ulterior cantitatea în așteptare fără o nouă asociere
făcută de Achiziții. Asocierea este necesară pentru marfa fără comandă sau pentru
schimbarea sursei restului, de exemplu surplus acoperit de o comandă suplimentară.

### Esențial pentru întreținerea codului

- `origin_item_id` leagă o poziție de acceptare ulterioară de poziția sosită fizic.
  Poziția nouă păstrează propria comandă; nu reprezintă o a doua sosire.
- `accepted_quantity` păstrează acceptarea de pe poziția respectivă;
  `resolved_quantity` însumează acceptările ulterioare ale poziției fizice.
  Cantitatea sosită rămâne egală cu acceptat inițial + acceptat ulterior + respins
  + în așteptare.
- Detaliul recepției confirmate expune pozițiile fizice în `items`, fiecare cu
  `total_accepted_quantity` și lista `acceptances`. Nu se adună încă o dată cantitatea
  sosită a pozițiilor de acceptare.
- Livrarea și disponibilul pentru facturi folosesc cantitățile acceptate pe surse,
  inclusiv pozițiile ulterioare; nu adaugă din nou contorul `resolved_quantity`.
- `version` împiedică salvarea pe o versiune veche. Blocările PostgreSQL protejează
  și restul comun al comenzii atunci când două recepții sunt acceptate simultan.
- Decizia, stocul și auditul sunt în aceeași tranzacție: un eșec le anulează împreună.

Integrarea noilor clarificări în emailurile periodice urmează după stabilizarea
acestui flux, în pachetul de notificări de mai jos.

### Scenarii de acceptanță pentru pachet

| Scenariu verificat | Rezultat |
| --- | --- |
| Sosesc 10 bucăți fără comandă | Sosirea se păstrează, toate 10 sunt în așteptare, stocul nu crește. |
| Produsul nu există în catalog | Se păstrează descrierea sosirii; acceptarea cere identificarea în catalog. |
| Din 10 în așteptare se acceptă 6, acoperite de comandă | Stocul crește cu 6, rămân 4 în așteptare, livrarea reflectă numai cele 6. |
| Cele 4 rămase sunt respinse | Stocul rămâne 6, nu mai există cantitate în așteptare, istoricul păstrează ambele decizii. |
| Se încearcă acceptarea peste restul comenzii | Operația este refuzată fără modificări parțiale. |
| Un surplus este acoperit printr-o comandă suplimentară | Noua acceptare are sursa corectă; acceptările anterioare își păstrează sursa și istoricul. |
| Factura cere și marfa încă în așteptare | Factura rămâne blocată pentru cantitatea neacoperită. |
| Marfa este clarificată și acceptată | Numai cantitatea acceptată și liberă devine eligibilă; asocierea și reverificarea pot permite verificarea facturii. |
| Aceeași cantitate este decisă simultan în două sesiuni | Cantitatea nu este consumată de două ori și nu există intrări duplicate în stoc. |
| O echipă încearcă operația altei echipe | Backendul refuză operația, indiferent de accesul direct la API. |

Scenariile principale sunt parcurse în browser, iar validările, permisiunile,
concurența și anularea la eșec sunt verificate și în testele backend.

## 6. Pachetele următoare, în ordinea propusă

1. **Trasabilitate și notificări:** extinderea istoricului accesibil pe documente, clarificări
   trimise echipei responsabile, SMTP configurabil și worker pornit permanent.
2. **Facturi și curs EUR:** scenarii complete pentru conversie și zile fără curs;
   apoi, dacă includem completarea, totaluri declarate și documente justificative.
3. **Evidența completă a stocului:** ieșiri, retururi și ajustări, cu reguli explicite
   pentru efectele asupra recepțiilor și facturilor deja asociate.
4. **Docker și livrare:** toate serviciile, configurare exemplu fără secrete,
   migrare și creare administrator, ghid de pornire și demonstrație pe mediu curat.
5. **Acceptanță finală:** scenariile cerute și testele relevante, lista limitărilor
   asumate și checkpoint Git la cererea utilizatorului.

## 7. Cum continuăm lucrul

- Chiar și un pachet mai mare se construiește în etape explicabile, cu un rezultat
  complet de testat la final.
- După fiecare etapă explicăm pe scurt conceptele esențiale din cod și motivul lor.
- Interfața și explicațiile sunt în română; comentariile din cod sunt simple și în engleză.
- Rulăm teste relevante în timpul lucrului și verificări mai ample la finalul unui pachet.
- Testele automate folosesc date izolate de datele utilizatorului.
- Commit și push se fac numai când utilizatorul le cere explicit.
