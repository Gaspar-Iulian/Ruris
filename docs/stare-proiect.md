# Starea proiectului și planul de livrare

Data evaluării: 21 octombrie 2026.

Acest document separă funcțiile implementate de lucrările propuse. Pachetele
pentru excepțiile de la recepție, trasabilitate/notificări, reconcilierea facturilor și documente atașate sunt implementate
și verificate; lucrările ulterioare sunt enumerate separat.

## 1. Obiectivul aplicației

Achizițiile, Depozitul și Contabilitatea folosesc aceleași documente și cantități,
cu permisiuni diferite. O factură poate fi aprobată numai când este acoperită de
marfă acceptată și corespunde condițiilor comenzii. Întârzierile și blocajele
trebuie să ajungă la persoanele responsabile, iar operațiile să poată fi urmărite.

Tehnologii folosite: Python, Flask, SQLAlchemy, PostgreSQL, React, bcrypt și JWT.
Profilul Docker `app` pornește întregul portal: Nginx/React, Flask/Gunicorn,
PostgreSQL, migrarea și workerul permanent, cu volume pentru bază și documente.
Există proceduri verificate de backup și restaurare, descrise în [ghidul Docker](docker.md).

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
| Corectarea facturilor | Schimbarea pozițiilor cere eliberarea asocierilor. Totalurile de pe document se pot corecta separat, cu motiv și versiune, păstrând asocierile. Schimbările invalidează verificarea anterioară. |
| Anularea facturilor | Numai înainte de aprobare, cu motiv, autor și moment. Eliberează asocierile și închide blocajele; păstrează pozițiile, fișierele și auditul, fără schimbarea stocului. |
| Totaluri furnizor | Net, TVA și total introduse separat din document și comparate cu sumele calculate. Totalurile lipsă, aritmetica inconsistentă și diferențele de un ban blochează verificarea. |
| Curs valutar | Curs istoric BNR din data exactă a facturii, preluat automat, cu sursa și conversia păstrate. Lipsa publicării și eșecul preluării au explicații distincte și permit reverificarea. Calculele monetare folosesc Decimal. |
| Audit | Istoric vizibil pentru comenzi, recepții și facturi, cu autor, moment și schimbări înainte/după. Auditul este atomic și protejat împotriva modificării sau ștergerii. Vizibilitatea respectă rolul și documentul, inclusiv eliminarea câmpurilor financiare și a notelor comerciale din istoricul comenzilor văzut de Depozit. |
| Documente atașate | PDF/PNG/JPG, maximum 10 MB, pentru comenzi, recepții și facturi. Descărcare autentificată, SHA-256, retragere cu motiv, audit și păstrarea fișierelor pe disc la repornire. Acces pe rol și document; facturile cer reverificare după modificarea fișierelor. |
| Notificări | Worker permanent în Docker, sumar zilnic pentru întârzieri, facturi blocate și clarificări direcționate pe echipe. Jurnal personal în portal, deduplicare, reîncercări și tratarea rezultatelor neclare. SMTP extern cu TLS este configurabil; mediul local folosește Mailpit. |
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
| Trasabilitate accesibilă echipelor | Istoric vizibil pentru cele trei tipuri de documente, cu acces limitat pe rol. | Istoricul administrării conturilor poate fi adăugat separat; evenimentele sale există deja în audit. |
| Emailuri periodice utilizabile la livrare | Worker pornit în Docker, SMTP configurabil, clarificări pe echipe și jurnal personal; Mailpit real verificat. | Configurarea și validarea unui furnizor SMTP în mediul de livrare, cu datele acelui mediu. Trimiterea externă nu a fost executată în teste. |
| Curs în ziua facturii | Este folosită strict data facturii; blocajele sunt explicate în portal. Sunt testate fluxul EUR până la plată, reluarea după eșec și reutilizarea cursului salvat. | O regulă alternativă pentru zile fără curs trebuie decisă explicit. Testele browser folosesc XML controlat; conexiunea publică BNR este verificată separat. |
| Stoc complet | Sunt implementate intrările din recepții acceptate. | Pentru un depozit cu consum și retururi: ieșiri, retururi și ajustări documentate. Până atunci, soldul reflectă numai intrările înregistrate. |
| Portabilitate pe alt PC | Portal complet în Docker, verificat pe volume goale; backup și restaurare în proiect separat, inclusiv fișiere. | Configurarea infrastructurii destinație; datele se mută prin backup, separat de cod. |
| Livrare în Git | Repository configurat și checkpointuri publicate anterior; există lucrări ulterioare în spațiul local. | Checkpoint final și push numai la cererea utilizatorului, apoi verificarea instrucțiunilor de pornire. |

### Completări utile, distincte de cerințele explicite

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
| Clarificare fără comandă, apoi asociere comercială | Emailul inițial ajunge în Mailpit pentru Achiziții; după asociere, sumarul pentru marfa de acceptat ajunge la Depozit. Jurnalele personale afișează mesajele permise; Depozitul nu primește jurnalul facturilor. |

Scenariile de mai sus folosesc facturi în RON. Pachetul de reconciliere adaugă
fluxurile EUR descrise mai jos. Trimiterea prin SMTP extern nu a fost executată.

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

Pentru pachetul de trasabilitate/notificări au trecut 115 teste backend pentru
istoric, transporturi, programare, deduplicare și concurență, cu Mailpit real
activat. După ultimele completări au trecut separat 43 de teste relevante.
Au trecut 112 teste de interfață și toate cele 8 fluxuri complete cu API real,
inclusiv istoricul unei facturi plătite și emailurile de clarificare. Selecțiile
backend se suprapun; nu reprezintă un total de teste distincte.
Ultima corecție de afișare a fost verificată prin 9 teste relevante de interfață
și buildul final; selecțiile de interfață se suprapun și ele.

Migrarea curentă `0022_notification_channels` este aplicată și verificată, iar
documentele și stocul au rămas neschimbate. Containerul workerului este pornit;
repornirea sa a fost verificată fără mesaje sau încercări de trimitere duplicate.

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

Clarificările sunt integrate în emailurile periodice, în pachetul descris mai jos.

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

## 6. Pachet implementat: trasabilitate și notificări

### Ce poți testa în portal

1. Deschide o comandă și apasă **Istoric**, apoi **Modificări** pentru valorile
   înainte și după. Achizițiile și Contabilitatea văd datele comerciale permise;
   Depozitul vede doar datele operaționale.
2. Din Contabilitate, deschide o factură și istoricul său: asocieri, blocaje,
   verificare, aprobare și plată. Accesul altor echipe la acest istoric este refuzat.
3. Din contul unei echipe, deschide **Notificări**. Vezi numai mesajele contului
   tău și tipurile compatibile cu rolul actual, cu încercări și starea livrării.
4. Emailurile aplicației se consultă în Mailpit la <http://127.0.0.1:8025>;
   testele automate folosesc un inbox separat la <http://127.0.0.1:8026>, cu prefix `[TEST]`.
   Configurația și comenzile de previzualizare/procesare sunt în README.

Pagina **Clarificări** arată recepțiile cu marfă încă în așteptare. După
rezolvare, acestea dispar din lista activă. Emailurile trimise se păstrează în
**Notificări**, pentru contul destinatar. O pagină Clarificări goală nu implică
ștergerea istoricului mesajelor. Butonul **Vezi notificările** leagă cele două pagini.

### Responsabilitatea clarificărilor

- Fără o comandă compatibilă cu rest disponibil: Achiziții. Dacă există un
  responsabil eligibil al comenzii, mesajul îi revine; altfel este adresat echipei active.
- Cu acoperire comercială disponibilă: Depozit, pentru decizia de acceptare sau respingere.
- Pentru acoperire parțială, cantitățile sunt împărțite în cele două sumaruri.
  Disponibilul comun al unei comenzi nu se repetă pentru mai multe recepții.
- Emailurile nu includ prețuri și nu rezervă cantități. Operațiile din portal
  verifică din nou situația curentă.

### Cum rulează workerul

`docker compose --profile notifications up -d --build notification-worker`
pornește migrările și workerul, cu repornire automată cât timp Docker este activ.
Mediul local este configurat pentru Mailpit. SMTP extern poate folosi STARTTLS
sau SSL, cu verificarea certificatului și autentificare configurabilă.

Programarea implicită este zilnic la **08:00 Europe/Bucharest**, cu verificare
la 60 de secunde. Pornirea după această oră recuperează sumarul zilei. Jurnalul
din PostgreSQL previne retrimiterea după repornire.

Există cel mult un sumar pe zi pentru utilizator, tip și transport. Situațiile
noi după un sumar trimis intră în procesarea zilei următoare. Un mesaj neactual
înainte de trimitere este omis. Eșecurile certe au maximum trei încercări;
rezultatele neclare nu sunt retrimise automat. Încercările întrerupte mai vechi
de 10 minute sunt marcate ca neclare la verificarea workerului.

„Acceptat de server” confirmă predarea către SMTP; inboxul destinatarului nu
este verificat de aplicație. Trimiterea prin SMTP extern trebuie validată cu
furnizorul și configurația mediului unde va fi livrat proiectul.

### Esențial din cod

- **Proiecția în SQL** întoarce numai câmpurile permise pentru istoricul Depozitului.
  O interfață care ascunde prețul nu înlocuiește această regulă din backend.
- **Outbox** înseamnă că mesajul și starea procesării sunt păstrate în baza de date,
  inclusiv între două porniri ale workerului.
- **Deduplicarea** folosește o regulă unică în PostgreSQL, nu doar o variabilă în memorie.
- **TLS** protejează conexiunea la serverul SMTP extern. Datele de autentificare
  rămân în configurația mediului.
- **Workerul separat** procesează emailurile independent de cererile utilizatorilor.

## 7. Pachet implementat: totaluri furnizor și fluxuri EUR

1. La crearea facturii introduci **Net factură**, **TVA factură** și **Total factură**
   din documentul furnizorului. O ciornă poate fi salvată fără aceste valori, dar
   verificarea o blochează până la completare.
2. Detaliul compară sumele din poziții cu cele de pe document și afișează diferențele
   în moneda facturii. Nu există toleranță automată, nici pentru un ban.
3. **Editează totalurile** permite corectarea înainte de aprobare, cu **Observații
   operație**, păstrând asocierile active. După salvare, factura cere reverificare.
4. Pentru EUR, verificarea preia cursul din ziua facturii. Un eșec de preluare sau
   validare permite **Reîncearcă preluarea cursului**. Un XML valid fără acea dată
   produce un blocaj distinct; nu se aplică automat cursul zilei anterioare.
5. Cursul valid se păstrează și se reutilizează. Aprobarea repetă verificările;
   plata păstrează conversia aprobată. Sursa și data cursului sunt vizibile în portal.

### Date existente

Migrarea `0023_invoice_declared_totals` adaugă trei coloane opționale, fără să
inventeze valorile documentelor vechi. O factură veche neaprobată, fără totaluri
declarate, cere completarea lor la următoarea verificare sau aprobare. Documentele
deja aprobate ori plătite își păstrează starea și nu se modifică prin acest flux.

### Scenarii verificate

- Factură EUR de 10,00, curs de test 5,123400: 51,23 RON, cu rotunjire la doi
  zecimali, verificare, aprobare și înregistrarea plății în browser.
- Preluare indisponibilă: blocaj; după reluare, verificare reușită. Aprobarea
  folosește cursul salvat chiar dacă sursa devine din nou indisponibilă.
- XML fără data facturii: blocaj explicit, fără conversie și fără aprobare,
  chiar dacă există în cache un curs pentru altă dată.
- Total declarat cu un ban mai mare: blocaj; corectarea păstrează marfa asociată,
  auditul și istoricul, iar reverificarea permite continuarea.
- Totaluri lipsă, incomplete, negative sau cu precizie excesivă; corectare cu
  versiune veche, acces din alt rol și eșec de audit: refuz sau anulare atomică.

Testele browser folosesc Flask și PostgreSQL reale, dar XML BNR controlat în
serverul de test. Rata 5,123400 este exclusiv o valoare de test. Preluarea HTTPS
din arhiva publică BNR a fost verificată separat pentru 2025-01-03: 4,974900.
Codul de producție nu conține aceste rate sau rute de configurare a testelor.

Verificarea pachetului: 269 de teste backend pentru facturi, cursuri și recepții,
17 teste ale formularului de factură și 11 fluxuri complete în browser au trecut.
Auditul, istoricul, notificările facturilor blocate și concurența alocărilor au
fost verificate separat. Buildul frontend și `flask db check` au trecut.
Migrarea este aplicată local; schemele browser temporare au fost eliminate.
Documentele existente și soldul de 175,000 au rămas neschimbate la verificare.

### Esențial din cod

- `declared_totals` păstrează ce scrie pe document; sumele calculate rămân separate.
- `Decimal` și `ROUND_HALF_UP` evită erorile de calcul ale numerelor în virgulă mobilă.
- Corectarea folosește o tranzacție cu audit și control de versiune; schimbările
  concomitente nu pot suprascrie în tăcere o versiune mai nouă.
- Un curs salvat este imuabil și legat de data facturii; conversia nu se schimbă
  la fiecare accesare sau după o problemă de rețea.

## 8. Pachet implementat: documente justificative

În detaliile unei comenzi, recepții sau facturi, apasă **Documente**. Poți
încărca un fișier, completa observații și descărca documentele permise rolului.
Fișierele greșite se retrag cu motiv; istoricul și conținutul sunt păstrate.
Nu există înlocuire în loc sau ștergere.

- Achizițiile gestionează fișierele comenzilor. Contabilitatea le consultă în
  limitele vizibilității comenzii; Depozitul nu le primește.
- Depozitul gestionează fișierele recepțiilor. Celelalte două echipe le consultă
  după confirmarea recepției.
- Contabilitatea gestionează fișierele facturilor înainte de aprobare. Încărcarea
  și retragerea cer reverificare, păstrând asocierile cu marfa acceptată.
- Facturile aprobate sau plătite permit consultarea fișierelor existente.
- Numele de pe disc este aleator. SHA-256 și dimensiunea sunt verificate înainte
  de descărcare. Metadatele și istoricul sunt protejate în PostgreSQL.
- Reîncercarea aceleiași încărcări nu creează duplicate. Un rezultat incert cere
  consultarea situației curente; fișierele cu un commit incert nu sunt șterse automat.

Migrarea este `0024_document_attachments`. Fișierele sunt implicit în
`instance/attachments`, excluse din Git și păstrate între reporniri.
Comanda `flask --app app check-attachments` verifică integritatea și raportează
fișiere neasociate sau temporare, fără modificări.
Pentru mutare sunt necesare împreună baza și directorul de fișiere.

### Cum testezi

1. Achiziții: deschide o comandă → **Documente**, încarcă un PDF cu observații,
   descarcă-l și consultă evenimentul din istoric.
2. Contabilitate: verifică accesul la acel PDF; Depozitul nu trebuie să vadă secțiunea.
3. Depozit: atașează avizul sau o fotografie unei recepții confirmate; Achizițiile
   și Contabilitatea pot consulta dovada.
4. Contabilitate: atașează PDF-ul unei facturi verificate. Starea revine Ciornă,
   asocierile rămân. Retrage fișierul greșit cu motiv și adaugă varianta corectă.
5. Reverifică și aprobă. Documentele existente rămân disponibile; modificarea
   fișierelor nu mai este permisă în fluxul obișnuit.

Verificări: 76 de teste backend relevante au trecut, inclusiv concurență reală;
121 de teste UI și 14 fluxuri complete prin browser au trecut. Cele trei fluxuri
noi verifică documentele comenzilor, recepțiilor și facturilor, cu descărcări
comparate prin SHA-256 și nume cu diacritice.
Testele complete folosesc un frontend separat pe 5174 și API temporar pe 5201,
prin proxy HTTP real, fără interceptarea și rescrierea cererilor în browser.
Datele și directorul de fișiere ale testului sunt temporare.

Regulile API, stocarea și backupul sunt descrise în [ghidul atașamentelor](atasamente.md).

### Esențial din cod

- `storage_key` este numele intern aleator al fișierului; numele original este
  doar metadată, pentru afișare și descărcare.
- `upload_key` identifică operația: o reîncercare cu aceleași date întoarce același
  document, fără o a doua încărcare sau un al doilea audit.
- `content_sha256` verifică dacă sunt descărcați exact octeții înregistrați.
- Tranzacția SQL păstrează împreună metadatele, versiunea și auditul. Fișierele
  se scriu separat; eșecurile cunoscute și commiturile incerte au tratamente distincte.

### Liste detaliate în portal

- Recepțiile afișează fiecare produs, comenzile asociate, unitatea și cantitățile
  sosite, acceptate, respinse și în așteptare. Acceptările ulterioare sunt reunite
  pe poziția inițială, fără dublarea cantității sosite.
- Clarificările afișează numai pozițiile cu marfă rămasă în așteptare.
- Facturile afișează numele furnizorului, produsele, comenzile asociate, cantitățile,
  prețurile, TVA, totalul fiecărei poziții, totalul documentului și scadența.
- Întârzierile includ furnizorul și balanța comandat / acceptat / rest, cu unitatea.
- Furnizorii includ codul fiscal și emailul pentru Achiziții și Contabilitate.
  Depozitul păstrează proiecția operațională existentă.
- API-ul încarcă datele pozițiilor pentru documentele paginii curente;
  paginarea continuă să numere documente, nu rândurile produselor.
- Cantitățile din portal ascund zerourile zecimale inutile: `5.000` devine `5`,
  `5.500` devine `5,5`. Formatarea folosește texte, fără rotunjire sau modificarea
  preciziei din baza de date; prețurile și sumele păstrează formatul monetar.

### Informații utile înainte de salvare

- Comenzile și facturile arată netul, TVA și totalul pe poziție și pe document,
  actualizate la modificarea cantității, prețului sau cotei TVA.
- Previzualizarea folosește `BigInt` și rotunjire pe fiecare poziție, la fel ca
  backendul. Pozițiile incomplete sau sumele peste limita permisă nu produc
  un total parțial prezentat drept total al documentului.
- Sumele de pe factura furnizorului rămân introduse independent. Formularul
  arată diferențele de net, TVA și total și verifică egalitatea net + TVA = total.
- La facturarea din comandă apar condițiile comerciale inițiale și avertizări
  pentru diferențe sau cantități fără marfă disponibilă pentru asociere.
- Recepția arată surplusul față de restul comenzii; confirmarea arată imediat
  cât mai este de repartizat sau cu cât se depășește cantitatea sosită.
- Detaliile documentului includ furnizorul, datele relevante și referința avizului.
  Valorile comenzilor sunt afișate doar pentru Achiziții și Contabilitate.

Verificări: suita UI de 138 de teste a fost parcursă; cazul de accesibilitate
corectat și celelalte verificări afectate au trecut la rerulare. Trei fluxuri
reale au trecut: recepția 77 + 23 cu facturare și plată, corectarea totalurilor
furnizorului și surplusul acoperit de o comandă suplimentară. Totalurile din
formular au fost comparate cu valorile calculate de backend la salvare.

### Facturi multiple pentru aceeași comandă

- Formularul arată facturile existente legate de comandă, cu starea și
  cantitățile înregistrate. Include și legăturile cunoscute prin recepții pentru
  facturile introduse manual, cu cantitatea efectiv asociată.
- Cantitatea propusă este restul comenzii neînregistrat pe facturi, în locul
  cantității integrale. Ciornele și facturile blocate sunt incluse în evidență.
  Dacă restul este zero, formularul propune zero și cere o cantitate pozitivă
  pentru salvare; depășirea manuală afișează avertizarea de posibil duplicat.
- Înregistrarea unui document distinct primit de la furnizor rămâne posibilă,
  inclusiv dacă este greșit. Verificarea și aprobarea cer cantități acoperite
  integral de recepții acceptate, fără reutilizarea cantităților deja asociate.
- Nu există regula „o singură factură pentru fiecare comandă”: facturile pentru
  tranșe diferite sunt valide. Duplicarea aceleiași referințe de factură la același
  furnizor este interzisă separat de baza de date.

### Pachet Docker complet

- Profilul `app` a fost pornit pe volume goale, cu migrare automată, React/Nginx,
  Flask/Gunicorn și worker permanent. Imaginile folosesc utilizatori fără root
  pentru procesele web și dependințe Python fixate în lockfile.
- Au trecut 22 de verificări backend pentru configurarea proxy-ului, disponibilitate
  și cookie-uri/JWT. Două fluxuri browser au trecut direct prin containere:
  recepție cu document și comanda 100 → recepții 77 + 23 → factură → plată.
- Backupul bazei și fișierelor a fost restaurat într-un proiect separat, cu alt
  utilizator PostgreSQL. Testul browser a confirmat conturile, stocul, factura
  plătită și conținutul SHA-256 al documentului descărcat.
- Backupul corupt și destinația cu fișiere existente au fost respinse înainte
  de suprascriere. Datele și fișierele proiectului principal au fost păstrate;
  cele două atașamente locale au fost copiate și verificate în volumul Docker.
- Portalul principal folosește acum `http://127.0.0.1:8080`. Instrucțiunile sunt
  în [docker.md](docker.md), inclusiv importul documentelor locale și restaurarea.

### Acceptanță, anulare și documentație de livrare

Checkpointul anterior a fost publicat pe `master`: `ef9bf65`, cu mesajul
`Added Full Docker Setup , Backup Restore , Detailed Tables , Live Totals , Invoice Safeguards , Mail Test Isolation`.
Pachetul descris aici este ulterior acelui commit și este inclus în checkpointul
următor, împreună cu README-ul compact și documentația de livrare.

- Migrarea `0025_invoice_cancellation` și fluxul complet de anulare sunt implementate.
  Facturile DRAFT/BLOCKED/VERIFIED pot fi anulate de Contabilitate, cu motiv și
  versiune. APPROVED/PAID sunt refuzate. Asocierile se eliberează atomic și nu
  mai consumă restul comenzii; documentul și referința sa rămân în evidență.
- Au trecut **1.073 de teste backend**, inclusiv SMTP separat și concurență reală.
  Aprobarea și anularea simultană au un singur câștigător, cu date coerente.
- Au trecut **146 de teste UI**, cu un test Docker exclus din execuția obișnuită.
  Cele **15 fluxuri cu Flask/PostgreSQL reale** au trecut: 14 la prima execuție,
  iar scenariul rămas la rerulare după corectarea așteptării vechi privind
  afișarea cantităților fără zerouri inutile. Compilarea frontendului a trecut.
- Un flux nou a trecut prin Nginx/Gunicorn Docker: anulare, eliberare de cantități,
  descărcarea PDF-ului și aprobarea facturii corecte.
- Backupul limitat la schema `public` și fișiere a fost restaurat într-un proiect
  gol, cu alt utilizator PostgreSQL. Restaurarea păstrează schema `public`
  precreată, fără să încerce recrearea ei. Au trecut două teste browser pe copia
  restaurată: stoc/factură plătită/document și factură anulată/motiv/audit/PDF SHA-256.
- Portalul principal a fost actualizat la migrarea 0025. `flask db check` nu
  detectează diferențe față de modele. La verificare au rămas 4 conturi, 7 recepții,
  5 facturi și 2 atașamente valide; nu au fost anulate documentele utilizatorului.
- README a fost restrâns la pornire, funcții și limite. Regulile, schema datelor,
  [matricea de acceptanță](acceptanta.md) și [scenariul de interviu](demo-interviu.md)
  descriu comportamentul actual, separat de extinderile viitoare.

Rezultatele de mai sus sunt verificarea actuală din 21 octombrie 2026. Numerele
mai mici din secțiunile precedente descriu etapele istorice și nu se însumează.

### Ajustări după testarea manuală

- Istoricul recepțiilor grupează operația și pozițiile ei, cu motiv afișat o
  singură dată și detalii extensibile. Paginarea numără operații întregi;
  evenimentele originale de audit rămân intacte.
- La factură și recepție, selectorul comenzii arată furnizorul și produsul,
  cantitatea și livrarea. Rezumatul selecției afișează cantități și termene;
  prețurile sunt afișate numai în formularul Contabilității.
- Listele de comenzi, recepții și facturi sunt prioritizate în baza de date
  înainte de paginare; catalogul și conturile pun înregistrările active primele.
  Ordinea exactă este în [procese.md](procese.md).
- Au trecut 449 de teste backend relevante, 110 teste UI existente și trei
  verificări noi pentru istoric și detaliile comenzilor, inclusiv pe mobil.
  Două fluxuri cu API real au trecut: 77 + 23 până la plată și anularea unui
  duplicat cu păstrarea fișierului. Compilarea frontendului și imaginile Docker
  au trecut. Aceste selecții includ teste comune și nu se adună cu suita anterioară.

## 9. Pachetele următoare, în ordinea propusă

1. **Acceptanța manuală finală:** parcurgerea ghidului de demonstrație cu utilizatorul,
   apoi checkpoint Git la cerere. Verificările automate și documentația sunt pregătite.
2. **Evidența completă a stocului, ca extindere:** ieșiri, retururi și ajustări, cu reguli explicite
   pentru efectele asupra recepțiilor și facturilor deja asociate.
3. **Demonstrație finală:** prezentarea aplicației și a deciziilor tehnice pentru interviu.

## 10. Cum continuăm lucrul

- Chiar și un pachet mai mare se construiește în etape explicabile, cu un rezultat
  complet de testat la final.
- După fiecare etapă explicăm pe scurt conceptele esențiale din cod și motivul lor.
- Interfața și explicațiile sunt în română; comentariile din cod sunt simple și în engleză.
- Rulăm teste relevante în timpul lucrului și verificări mai ample la finalul unui pachet.
- Testele automate folosesc date izolate de datele utilizatorului.
- Commit și push se fac numai când utilizatorul le cere explicit.
