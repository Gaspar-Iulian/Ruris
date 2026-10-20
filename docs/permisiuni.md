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

`roles_required()` autentifica cererea si verifica rolurile declarate explicit.
O lista de roluri goala sau un rol necunoscut produce eroare la configurarea rutei.
Se pot declara mai multe roluri pentru o operatie comuna.
ADMIN are doar permisiunile declarate pentru el.

- 401: sesiune lipsa, invalida, expirata, revocata sau cont inactiv.
- 403: sesiune valida, dar rolul nu permite operatia.
- 503: baza nu permite verificarea sau citirea datelor; accesul nu este acordat.

Schimbarea rolului modifica accesul la urmatoarea cerere, fara un login nou.
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

## Matricea pentru modulele viitoare

Aceste operatii nu sunt implementate inca. Matricea ghideaza construirea lor.

| Operatie | Rol care modifica | Informatii necesare altor echipe |
| --- | --- | --- |
| Creare si confirmare comanda | ACHIZITII | Depozitul vede produsele, cantitatile si termenele; contabilitatea vede si preturile pentru verificare |
| Confirmare receptie | DEPOZIT | Achizitiile si contabilitatea vad cantitatile acceptate si diferentele relevante |
| Iesire, retur, ajustare de stoc | DEPOZIT | Achizitiile si contabilitatea vad efectele relevante propriului flux |
| Inregistrare si verificare factura | CONTABILITATE | Achizitiile vad diferentele pentru care trebuie sa discute cu furnizorul |
| Aprobare factura si evidenta platii | CONTABILITATE | Acces limitat la starea necesara fluxului |
| Schimbare rol si activare/dezactivare conturi | ADMIN | Fiecare utilizator isi poate consulta propriile date prin /me |

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
