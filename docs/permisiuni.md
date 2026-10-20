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

POST /api/invoices, GET /api/invoices si GET /api/invoices/{id} sunt disponibile
exclusiv rolului CONTABILITATE. Inclusiv ADMIN primeste 403.
Crearea si PATCH /api/invoices/{id} necesita JWT valid si protectie CSRF.
Editarea este permisa numai in DRAFT, cu version si reason obligatorii.
Nu exista inca verificare, aprobare sau plata. Celelalte echipe nu pot consulta ciornele facturilor.

## Matricea pentru modulele viitoare

Aceste operatii nu sunt implementate inca. Matricea ghideaza construirea lor.

| Operatie | Rol care modifica | Informatii necesare altor echipe |
| --- | --- | --- |
| Iesire, retur, ajustare de stoc | DEPOZIT | Achizitiile si contabilitatea vad efectele relevante propriului flux |
| Inregistrare si verificare factura | CONTABILITATE | Achizitiile vad diferentele pentru care trebuie sa discute cu furnizorul |
| Aprobare factura si evidenta platii | CONTABILITATE | Acces limitat la starea necesara fluxului |

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
