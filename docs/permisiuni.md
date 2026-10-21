# Permisiuni pe roluri

Fiecare cont are un singur rol in prima versiune.
Codurile sunt ADMIN, ACHIZITII, DEPOZIT si CONTABILITATE.
Etichetele pentru interfata sunt Administrator, Achiziții, Depozit si Contabilitate.
Rolul si starea contului sunt citite din PostgreSQL la fiecare cerere protejata.
JWT identifica utilizatorul; un camp role din token nu acorda drepturi.

## Comportamentul implementat

| Endpoint | Acces |
| --- | --- |
| GET /api/health | Public |
| POST /api/auth/login | Public, cu validare si limitarea incercarilor |
| GET /api/auth/me | Orice cont activ, cu sesiune valida |
| POST /api/auth/logout | Orice cont activ, cu sesiune valida si CSRF |
| GET /api/users | Doar ADMIN, cu sesiune valida |
| POST /api/users | Doar ADMIN, cu sesiune valida si CSRF; creeaza conturi pentru cele trei echipe |
| PATCH /api/users/<id>/status | Doar ADMIN, cu sesiune valida si CSRF; activeaza/dezactiveaza cu motiv |
| PATCH /api/users/<id>/role | Doar ADMIN, cu sesiune valida si CSRF; schimba rolul cu motiv |
| POST /api/suppliers | Doar ACHIZITII, cu sesiune valida si CSRF |
| PATCH /api/suppliers/<id> | Doar ACHIZITII, cu CSRF si motiv; nume si/sau email |
| PATCH /api/suppliers/<id>/status | Doar ACHIZITII, cu CSRF si motiv; dezactivare/reactivare |
| GET /api/suppliers | ACHIZITII, DEPOZIT si CONTABILITATE; proiectie limitata pentru depozit |
| POST /api/products | Doar ACHIZITII, cu sesiune valida si CSRF |
| GET /api/products | ACHIZITII, DEPOZIT si CONTABILITATE |
| PATCH /api/products/<id> | Doar ACHIZITII, cu CSRF si motiv; modifica numele |
| PATCH /api/products/<id>/status | Doar ACHIZITII, cu CSRF si motiv; dezactivare/reactivare |
| POST /api/purchase-orders | Doar ACHIZITII, cu sesiune valida si CSRF; creeaza ciorne |
| GET /api/purchase-orders | ACHIZITII vede toate; DEPOZIT si CONTABILITATE doar confirmate/inchise cu data confirmarii |
| GET /api/purchase-orders/<id> | Aceeasi vizibilitate ca lista; DEPOZIT fara preturi, TVA si moneda |
| GET /api/purchase-orders/<id>/delivery | Aceeasi vizibilitate ca detaliul; cantitati comandate, acceptate si rest de livrat, fara preturi |
| GET /api/purchase-orders/overdue | ACHIZITII, DEPOZIT si CONTABILITATE; pozitii intarziate din comenzi confirmate deschise, fara preturi |
| PATCH /api/purchase-orders/<id> | Doar ACHIZITII, cu CSRF, motiv si versiune; editare ciorna |
| POST /api/purchase-orders/<id>/confirm | Doar ACHIZITII, cu CSRF si versiune; confirma ciorna valida |
| POST /api/receipts | Doar DEPOZIT, cu sesiune si CSRF; ciorna din comanda confirmata |
| GET /api/receipts | DEPOZIT vede toate; ACHIZITII si CONTABILITATE doar confirmate cu data si autor de confirmare |
| GET /api/receipts/<id> | Aceeasi vizibilitate ca lista; antet si cantitati, fara preturi |
| PATCH /api/receipts/<id> | Doar DEPOZIT, cu CSRF, motiv si versiune; corecteaza antetul si cantitatile ciornei |
| POST /api/receipts/<id>/confirm | Doar DEPOZIT, cu CSRF, motiv si versiune; clasifica marfa si adauga intrarile acceptate |
| GET /api/stock | ACHIZITII, DEPOZIT si CONTABILITATE; cantitati disponibile, fara preturi |

`roles_required()` autentifica cererea si verifica rolurile declarate explicit.
O lista de roluri goala sau un rol necunoscut produce eroare la configurarea rutei.
Se pot declara mai multe roluri pentru o operatie comuna.
ADMIN are doar permisiunile declarate pentru el.

- 401: sesiune lipsa, invalida, expirata, revocata sau cont inactiv.
- 403: sesiune valida, dar rolul nu permite operatia.
- 503: baza nu permite verificarea sau citirea datelor; accesul nu este acordat.

Rolul se citeste din baza la fiecare cerere. Schimbarea prin API invalideaza sesiunile existente
si solicita un login nou pentru folosirea noului rol.
Dezactivarea contului si invalidarea sesiunii sunt verificate inaintea rolului.
Erorile nu expun lista de utilizatori sau detaliile interne.

## Lista administrativa

`GET /api/users?page=1&per_page=20` permite administratorului sa consulte conturile.
Sunt afisate doar id, name, email, role si is_active.
Parolele, hashurile si versiunea sesiunilor nu sunt selectate pentru lista.
Conturile active si inactive sunt incluse, ordonate dupa ID.

`page` este intre 1 si 1000000; `per_page` este intre 1 si 100.
Parametrii duplicati si filtrele neimplementate sunt respinse cu 400.
Raspunsul include users si pagination: page, per_page, total, pages.
O pagina dupa sfarsitul listei returneaza users gol, cu totalul pastrat.
Raspunsurile au Cache-Control: no-store.

## Facturi in ciorna

GET /api/invoices/{id}/matching este exclusiv CONTABILITATE. Returneaza
recepțiile candidate, diferentele comerciale, disponibilul, asocierile active si
blocajele, pentru procesarea facturii. Operatiile de scriere folosesc in continuare
rutele existente cu JWT, CSRF, versiune si motiv unde este obligatoriu.

GET /api/purchase-orders/{id}/invoicing este exclusiv CONTABILITATE. Expune
datele comerciale ale comenzii si cantitatile acceptate, asociate activ facturilor
si disponibile, pentru precompletare. Celelalte roluri primesc 403.

POST /api/invoices, GET /api/invoices si GET /api/invoices/{id} sunt disponibile
exclusiv rolului CONTABILITATE. Inclusiv ADMIN primeste 403.
Crearea si PATCH /api/invoices/{id} necesita JWT valid si protectie CSRF.
Editarea este permisa in DRAFT, BLOCKED si VERIFIED, cu version si reason obligatorii,
fara alocari active. O schimbare efectiva revine la DRAFT si invalideaza verificarea.
Aprobarea si inregistrarea platii sunt descrise mai jos.
Celelalte echipe nu pot consulta facturile.

POST si GET /api/invoices/{id}/allocations sunt disponibile exclusiv CONTABILITATE.
Crearea alocarilor necesita JWT, CSRF, version si reason. POST
/api/invoices/{id}/allocations/release permite aceluiasi rol eliberarea integrala
a alocarilor selectate, cu aceleasi protectii. Editarea ciornei este blocata cat
timp exista alocari ACTIVE; liniile cu istoric de alocari nu pot fi eliminate.
Alocarea nu aproba factura si nu inregistreaza plata.

POST /api/invoices/{id}/verify si GET /api/invoices/{id}/issues sunt exclusiv pentru
CONTABILITATE. Verificarea necesita JWT, CSRF si version; lista motivelor include
istoricul paginat. Rolul responsabil salvat pe un blocaj nu acorda implicit acces
altor echipe la factura. Crearea si eliberarea alocarilor sunt permise si din
BLOCKED/VERIFIED; o astfel de schimbare invalideaza verificarea si revine la DRAFT.

POST /api/invoices/{id}/approve este exclusiv pentru CONTABILITATE, cu JWT,
CSRF, version si reason. Necesita VERIFIED si repeta verificarile sub blocare.
APPROVED pastreaza autorul si momentul aprobarii, iar modificarile, alocarile,
eliberarile si reverificarea obisnuita sunt respinse cu 409 pentru acest document.
Aprobarea nu transmite o plata catre banca.

POST /api/invoices/{id}/pay este exclusiv pentru CONTABILITATE, cu JWT, CSRF,
version, reason, paid_at si payment_reference. Necesita APPROVED, versiunea curenta
si absenta motivelor deschise. O factura PAID respinge modificarea si o a doua plata.
Aceasta operatie tine evidenta unei plati integrale; nu trimite ordine bancare.

Sumarul email al facturilor BLOCKED include doar motivele deschise si este adresat
conturilor active CONTABILITATE. Rolul, starea si adresa destinatarului sunt
recontrolate la preluarea mesajului pentru trimitere. Nu se trimit aceste sumaruri
catre ADMIN, ACHIZITII sau DEPOZIT. Transportul este configurabil; implicit este Mailpit local.

## Istoric și jurnalul notificărilor

- Istoricul comenzilor are aceeași vizibilitate ca documentul. Depozitul primește
  numai câmpurile operaționale proiectate în SQL; câmpurile financiare și notele
  comerciale nu sunt returnate în răspunsul API.
- Istoricul facturilor este disponibil numai Contabilității, inclusiv evenimentele
  de asociere, blocare, aprobare și plată.
- Jurnalul notificărilor returnează numai mesajele destinatarului autentificat,
  pentru tipurile compatibile cu rolul său actual. Schimbarea rolului nu permite
  consultarea mesajelor vechi rezervate altui departament.
- Clarificările fără acoperire comercială sunt adresate Achizițiilor; cantitățile
  cu acoperire disponibilă sunt adresate Depozitului. Emailurile nu includ prețuri
  sau totaluri financiare și nu acordă permisiuni suplimentare în portal.
- Conturile inactive sunt excluse, iar destinatarul și conținutul sunt recontrolate
  la preluarea mesajului. Administratorul nu vede implicit notificările de business.

## Documente atașate

Atașamentele sunt implementate cu reguli separate pe document:

| Document | Modifică fișierele | Consultă fișierele |
| --- | --- | --- |
| Comandă | Achiziții | Achiziții și Contabilitate, conform vizibilității comenzii |
| Recepție | Depozit | Depozit; Achiziții și Contabilitate numai după confirmare |
| Factură | Contabilitate, înainte de aprobare | Contabilitate |

Depozitul nu vede fișierele comerciale ale comenzilor, nici metadatele sau
evenimentele lor din istoric. Administratorul nu are acces implicit.
Fișierele retrase se păstrează și se pot descărca de către rolurile autorizate,
cu audit. Nu există ștergere sau modificare în loc. Detalii: [atașamente](atasamente.md).

## Matricea pentru modulele viitoare

Aceste operatii nu sunt implementate inca. Matricea ghideaza construirea lor.

| Operatie | Rol care modifica | Informatii necesare altor echipe |
| --- | --- | --- |
| Iesire, retur, ajustare de stoc | DEPOZIT | Achizitiile si contabilitatea vad efectele relevante propriului flux |
| Inregistrare si verificare factura | CONTABILITATE | Achizitiile vad diferentele pentru care trebuie sa discute cu furnizorul |
| Corectarea platii sau revocarea aprobarii | CONTABILITATE | Acces limitat la starea necesara fluxului |

Administratorul tehnic nu primeste automat dreptul de a confirma receptii sau de a aproba plati.
Accesul de citire intre echipe va avea campuri limitate in raspunsul API.
Verificam atat rolul, cat si documentul si campurile solicitate.
Lista si detaliul unui document, exportul si atasamentele trebuie sa respecte aceleasi reguli.

Rutele de business vor declara explicit rolurile permise.
React va afisa actiunile disponibile pe baza rolului, iar backendul va aplica regulile.
Rutele demonstrative pentru achizitii, depozit si facturi exista exclusiv in teste.

## Verificari

Testele acopera toate cele patru roluri, inclusiv operatii comune pentru mai multe roluri.
Verifica si refuzul accesului administrativ printr-un camp role adaugat in JWT,
contul inactiv, schimbarea rolului si paginarea fara expunerea secretelor.
