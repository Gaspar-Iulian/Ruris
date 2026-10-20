# Ruris

Aplicatie interna pentru achizitii, depozit si contabilitate.

Proiectarea este descrisa in [arhitectura](docs/arhitectura.md),
in [procesele si regulile aplicatiei](docs/procese.md)
si in [schema bazei de date](docs/schema-date.md).

## Tehnologii

- Backend: Python si Flask.
- Frontend: React si TypeScript.
- Baza de date: PostgreSQL.
- Parole: bcrypt.
- Autentificare: JWT.
- Rulare: Docker Compose.

## Structura

```text
Ruris/
|-- backend/
|   |-- app/
|   |   |-- models/
|   |   |-- routes/
|   |   `-- services/
|   `-- tests/
|-- frontend/
|   `-- src/
`-- docs/
    `-- arhitectura.md
```

- `models`: tabelele si relatiile bazei de date.
- `routes`: endpointurile API si verificarea accesului.
- `services`: regulile aplicatiei si integrarile externe.
- `tests`: verificarea regulilor si a permisiunilor.
- `frontend/src`: paginile si componentele React.
- `docs`: explicatii despre proiect.

## Stare

Backendul are un endpoint de verificare: GET /api/health.
Acesta verifica doar functionarea API-ului, fara conectare la baza de date.
Configurarea PostgreSQL prin Docker Compose este pregatita.
Flask incarca setarile din `.env` si initializeaza SQLAlchemy pentru PostgreSQL.
Modelul User si migrarea `0001_users` sunt pregatite.
Jurnalul de audit si migrarea `0002_audit_events` sunt pregatite.
PostgreSQL a fost pornit prin Compose, iar cele patru migrari au fost aplicate si verificate.
POST /api/auth/login autentifica un cont activ si emite JWT prin cookie.
GET /api/auth/me verifica sesiunea si returneaza datele curente ale contului.
POST /api/auth/logout revoca tokenul curent in PostgreSQL si sterge cookie-urile.
RBAC este implementat, iar lista utilizatorilor este accesibila doar rolului ADMIN.
POST /api/users permite administratorului sa creeze conturi pentru cele trei echipe, cu audit.
PATCH /api/users/<id>/status permite activarea si dezactivarea conturilor, cu audit.
PATCH /api/users/<id>/role permite schimbarea rolului, cu motiv si audit.
Modulele de business vor urma separat.
Flask-Migrate este configurat, iar folderul `backend/migrations` este initializat.

## Pornire backend pe Windows

La prima utilizare, creeaza `.env` din `.env.example` in radacina proiectului
si seteaza parola PostgreSQL si cheia JWT, conform sectiunilor de mai jos.

Din folderul proiectului, in PowerShell, cu Python instalat:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app run --debug
```

Mediul `.venv` pastreaza separat dependentele proiectului.
Comenzile folosesc direct Python din acest mediu, fara activare.
Serverul cu debug este doar pentru dezvoltare locala.

Deschide http://127.0.0.1:5000/api/health in browser.
Raspunsul asteptat este:

```json
{"status": "ok"}
```

Opreste serverul cu Ctrl+C in terminal.

## PostgreSQL pentru dezvoltare

Fisierul `compose.yaml` defineste deocamdata doar baza de date.
Backendul si frontendul vor fi adaugate ulterior.
Comenzile de mai jos se ruleaza din radacina proiectului, dupa pornirea Docker Desktop.

La prima configurare, copiaza modelul:

```powershell
Copy-Item .env.example .env
```

Editeaza `.env` si inlocuieste `POSTGRES_PASSWORD` cu o parola proprie.
`.env` este exclus din Git. `.env.example` documenteaza setarile fara secrete reale.

| Setare | Rol |
| --- | --- |
| POSTGRES_DB | Numele bazei de date |
| POSTGRES_USER | Utilizatorul PostgreSQL pentru dezvoltare locala |
| POSTGRES_PASSWORD | Parola utilizatorului PostgreSQL |
| POSTGRES_HOST | Adresa bazei de date folosita de Flask |
| POSTGRES_PORT | Portul disponibil pe calculatorul tau |

Utilizatorul creat de imaginea PostgreSQL are drepturi de administrator al bazei de date.
Pentru productie vom separa acest cont de utilizatorul aplicatiei.

Flask citeste acelasi `.env` ca Docker Compose, indiferent de folderul de pornire.
Variabilele deja definite in mediul procesului au prioritate fata de `.env`.
Cand Flask ruleaza local, POSTGRES_HOST este `127.0.0.1`.
Cand il vom rula in Compose, adresa va fi numele serviciului `db` si portul intern 5432.
Parola PostgreSQL este separata de parolele viitorilor utilizatori ai aplicatiei.

Porneste baza si asteapta sa fie pregatita:

```powershell
docker compose up -d --wait db
docker compose ps
```

- `image: postgres:17` foloseste imaginea oficiala PostgreSQL, versiunea majora 17.
- `ports` permite conectarea doar de pe calculatorul local, implicit la portul 5432.
- `postgres_data` pastreaza datele separat de container.
- `healthcheck` verifica daca PostgreSQL accepta conexiuni.
- `--wait` asteapta trecerea verificarii de disponibilitate.

Pentru oprire:

```powershell
docker compose down
```

Volumul si datele raman pastrate. Volumul nu inlocuieste un backup.
Setarile POSTGRES_DB, POSTGRES_USER si POSTGRES_PASSWORD initializeaza doar un volum gol.
Schimbarea lor in `.env` nu modifica automat o baza existenta.

Configurarea poate fi verificata si fara motorul Docker pornit:

```powershell
docker compose --env-file .env.example config --quiet
```

Aceasta comanda verifica fisierul Compose, fara sa porneasca PostgreSQL.

## Migrari

Migrarile descriu schimbarile tabelelor si se pastreaza in Git impreuna cu modelele.
Folderul `backend/migrations` este deja initializat; nu este nevoie de `db init` la clonare.
Prima migrare, `0001_users`, creeaza tabela utilizatorilor.
A doua migrare, `0002_audit_events`, creeaza jurnalul de audit si protectia lui la modificari.
A treia migrare, `0003_revoked_tokens`, creeaza tabela tokenurilor revocate.
A patra migrare, `0004_romanian_roles`, redenumeste rolurile echipelor in romana.
Migrarile sunt scrise manual si verificate prin generarea SQL pentru PostgreSQL fara conexiune.
Aplicarea, constrangerile si protectia auditului au fost verificate pe PostgreSQL.

Cand vom adauga un model, cu PostgreSQL pornit, din folderul `backend`:

```powershell
.\.venv\Scripts\python.exe -m flask --app app db migrate -m "Adauga furnizori"
.\.venv\Scripts\python.exe -m flask --app app db upgrade
```

- `db migrate` compara modelele cu baza si genereaza un fisier de modificari.
- Verificam fisierul generat inainte de aplicare.
- `db upgrade` aplica migrarile existente asupra bazei.

Pe un alt calculator se aplica migrarile livrate prin `db upgrade`.
Nu se genereaza din nou pentru aceleasi schimbari.
Nu folosim `db.create_all()` pentru crearea tabelelor aplicatiei.

Istoricul fisierelor de migrare poate fi consultat fara PostgreSQL:

```powershell
.\.venv\Scripts\python.exe -m flask --app app db history
```

## Utilizatori

Modelul `User` defineste numele, emailul unic, hashul parolei, rolul,
starea activ/inactiv, versiunea sesiunilor si momentele de creare/modificare.
Emailul se valideaza si se normalizeaza la litere mici, fara spatii la capete.
Rolurile permise sunt ADMIN, ACHIZITII, DEPOZIT si CONTABILITATE.
API-ul si baza folosesc aceste coduri. In interfata le vom afisa ca
Administrator, Achiziții, Depozit si Contabilitate.
Migrarea converteste rolurile existente fara schimbarea drepturilor, parolelor sau sesiunilor.
Valorile istorice din audit raman pastrate asa cum au fost inregistrate.
Nu exista rol implicit: acesta trebuie ales explicit.

`set_password()` foloseste bcrypt cu salt aleator si factor 12.
Parola trebuie sa aiba minimum 12 caractere si maximum 72 de octeti UTF-8.
Limita in octeti poate fi atinsa mai repede de caracterele cu diacritice.
Parolele prea lungi sunt respinse, fara trunchiere.
`check_password()` verifica parola fata de hash.
Schimbarea parolei creste `token_version`, pregatind invalidarea sesiunilor viitoare.
Loginul si verificarea contului prin JWT sunt implementate.
Verificarea rolurilor, listarea si crearea conturilor de echipa sunt implementate.
Activarea/dezactivarea si schimbarea rolului sunt implementate, cu audit si protectia ultimului administrator.

## Configurare JWT

Flask-JWT-Extended este initializat, iar endpointul de login emite tokenuri.
Pentru o instalare noua, genereaza local o cheie aleatoare:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copiaza rezultatul in `JWT_SECRET_KEY` din `.env`, fara sa il publici in Git.
Nu folosi o parola de utilizator sau parola PostgreSQL drept cheie JWT.
La aceasta instalare cheia a fost deja generata local; nu este necesara regenerarea ei.
Schimbarea cheii invalideaza tokenurile semnate cu cheia veche.

| Setare | Comportament |
| --- | --- |
| JWT_SECRET_KEY | Cheie obligatorie, minimum 32 de octeti, generata aleator |
| JWT_ACCESS_TOKEN_MINUTES | Durata tokenului: implicit 15 minute, configurabila intre 1 si 60 |
| JWT_COOKIE_SECURE | Implicit true; false doar pentru dezvoltarea locala prin HTTP |

Aplicatia refuza pornirea cu o cheie lipsa/prea scurta sau cu setari JWT invalide.
Nu exista o cheie implicita in cod.

Tokenul va fi semnat prin HS256 si transmis intr-un cookie HttpOnly,
cu SameSite=Lax si acces limitat la `/api`.
React nu va pastra tokenul in localStorage.
Pentru cererile POST, PUT, PATCH si DELETE autentificate prin cookie,
va trimite valoarea cookie-ului CSRF in antetul `X-CSRF-TOKEN`.
Cookie-ul CSRF este separat si poate fi citit de JavaScript; tokenul JWT nu poate.
Acest mecanism este descris in [documentatia Flask-JWT-Extended](https://flask-jwt-extended.readthedocs.io/en/stable/token_locations.html).

`.env.example` foloseste `JWT_COOKIE_SECURE=false` pentru HTTP local.
La publicarea prin HTTPS, configuram `JWT_COOKIE_SECURE=true`.
Loginul verifica starea activa a contului si emite un token cu ID-ul utilizatorului
si versiunea sesiunilor. Nu include parola, hashul sau emailul in token.
Orice ruta cu `jwt_required()` incarca acum contul din baza de date,
verifica starea activa si compara versiunea sesiunii cu cea din token.
Tokenurile revocate prin logout sunt refuzate pe toate rutele protejate.
Rutele pot declara rolurile permise prin `roles_required()`.
Reinnoirea sesiunii va fi adaugata separat daca fluxul o necesita.

## Login

Endpoint: `POST /api/auth/login`, cu `Content-Type: application/json`.

```json
{
  "email": "utilizator@example.com",
  "password": "<parola contului>"
}
```

Emailul este normalizat dupa aceeasi regula ca la crearea contului.
Parola se verifica exact cum a fost introdusa, fara eliminarea spatiilor.
La succes se raspunde cu mesajul si datele publice ale utilizatorului:
id, name, email si role. Tokenul apare doar in cookie-ul HttpOnly,
impreuna cu cookie-ul CSRF separat. Raspunsurile au `Cache-Control: no-store`.

| Status | Semnificatie |
| --- | --- |
| 200 | Cont activ si parola corecta; autentificare reusita |
| 400 | JSON invalid sau campuri necorespunzatoare |
| 401 | Email sau parola incorecta; acelasi raspuns si pentru cont inactiv |
| 403 | Origine externa nepermisa |
| 413 | Corp mai mare de 4096 de octeti |
| 415 | Corpul nu este JSON |
| 429 | Limita incercarilor gresite a fost atinsa |
| 503 | PostgreSQL sau auditul nu este disponibil |

Loginul accepta JSON si refuza Origin diferit de originea API-ului, precum si cererile
marcate cross-site. React va accesa `/api` prin aceeasi origine, folosind un proxy local
care pastreaza antetul Host. Clientii HTTP fara Origin pot apela API-ul direct.
Nu configuram CORS permisiv.

Sunt permise 10 incercari gresite pe minut per IP, apoi se raspunde cu 429 si Retry-After.
Incercarile reusite nu consuma limita, dar un IP deja limitat trebuie sa astepte.
Contoarele sunt momentan in memoria procesului, pentru dezvoltarea locala.
Ele se reseteaza la repornire si nu sunt comune intre procese.
Inainte de rularea cu mai multe procese vom folosi stocare comuna, de exemplu Redis.
Nu avem incredere automat in X-Forwarded-For; configurarea proxy-ului va fi explicita la publicare.

Succesul produce un eveniment LOGIN asociat contului autentificat.
Incercarile cu date invalide procesate de serviciu produc LOGIN_FAILED,
fara a pretinde ca persoana care a incercat este proprietarul contului.
Se pastreaza emailul declarat si IP-ul, fara parola, hash sau token.
Evenimentul foloseste `entity_type=authentication`, `entity_id=1` pentru serviciul de login,
cu `actor_process=authentication`. Aceasta referinta nu este un ID de utilizator.
Incercarile respinse inainte de verificarea credentialelor nu produc acest eveniment.
Tokenul este transmis numai dupa salvarea auditului cu succes.

## Contul autentificat

Endpoint: `GET /api/auth/me`, folosind cookie-ul primit la login.
Nu cere email, parola sau ID de utilizator in cerere.

```json
{
  "user": {
    "id": 1,
    "name": "Ana Test",
    "email": "ana@example.com",
    "role": "DEPOZIT"
  }
}
```

Verificarea JWT este comuna tuturor rutelor care folosesc `jwt_required()`:

1. Se verifica semnatura, expirarea, tipul tokenului si CSRF unde este necesar.
2. Identitatea trebuie sa fie un ID pozitiv valid pentru BIGINT.
3. `token_version` trebuie sa fie un numar intreg nenegativ.
4. Contul se reciteste din PostgreSQL, inclusiv rolul si starea activa.
5. Versiunea tokenului trebuie sa corespunda contului.

Rolul din baza are prioritate; nu avem incredere intr-un rol inclus in token.
Schimbarea parolei prin `set_password()` creste versiunea si invalideaza tokenurile vechi.
Dezactivarea contului blocheaza accesul chiar daca tokenul nu a expirat.
Acest pas nu implementeaza inca permisiuni pentru achizitii, depozit sau contabilitate.

Lipsa tokenului, tokenul invalid/expirat si sesiunea necorespunzatoare produc JSON cu status 401.
Erorile nu includ tokenul sau detaliile interne de validare.
Daca PostgreSQL nu permite verificarea sesiunii, raspunsul este 503; accesul nu este acordat.
Cookie-ul nu este sters automat la erori, inclusiv la lipsa CSRF.
`/me` nu reinnoieste tokenul si nu expune hashul parolei sau versiunea sesiunilor.
Raspunsurile au `Cache-Control: no-store`.

## Logout

Endpoint: `POST /api/auth/logout`, folosind cookie-ul JWT si antetul `X-CSRF-TOKEN`.
Antetul contine valoarea cookie-ului `csrf_access_token` primit la login.
Nu trimitem parola sau un token de revocat in corpul cererii.

La succes:

```json
{"message": "Deconectare reusita."}
```

Serviciul salveaza identificatorul unic al tokenului in `revoked_tokens`,
impreuna cu utilizatorul, expirarea si momentul revocarii.
Nu salveaza JWT-ul complet. Revocarea si evenimentul LOGOUT se confirma impreuna.
Abia apoi raspunsul sterge cookie-urile JWT si CSRF.

Verificarea revocarii consulta PostgreSQL la fiecare cerere protejata.
Un token copiat inainte de logout nu mai poate accesa `/api/auth/me` dupa revocare.
Lista revocarilor ramane in baza si nu depinde de memoria procesului Flask.
Logoutul invalideaza doar tokenul curent; alte sesiuni ale aceluiasi cont raman active.
Un login nou emite un token diferit si poate fi folosit normal.

Fara token, cu token expirat/revocat sau fara CSRF corect se raspunde cu 401.
Repetarea logoutului cu tokenul deja revocat produce 401, fara un nou eveniment LOGOUT.
O constrangere unica pe identificator previne revocari si audituri duplicate
si atunci cand doua cereri au trecut verificarea inaintea primei confirmari.

Daca revocarea sau auditul esueaza, raspunsul este 503 si cookie-urile nu sunt sterse.
Daca nu putem verifica revocarea, accesul la rutele protejate este refuzat temporar cu 503.
Inca nu exista o sarcina periodica pentru curatarea revocarilor expirate.
Aceasta va putea sterge doar intrari pentru tokenuri deja expirate, pastrand auditul.

## Acces pe roluri

`roles_required()` verifica sesiunea si permite doar rolurile declarate pentru operatie.
ADMIN nu are acces implicit la operatiile celorlalte echipe.
Sesiunea invalida produce 401; rolul insuficient produce 403.

Prima operatie administrativa este `GET /api/users`, disponibila doar pentru ADMIN.
Lista returneaza id, name, email, role si is_active, cu paginare si fara secrete.
Implicit se returneaza 20 de conturi per pagina; limita este 100.

Regulile implementate si matricea modulelor viitoare sunt in [permisiuni.md](docs/permisiuni.md).
Modulele de achizitii, depozit si facturi nu au inca endpointuri de business.
Testele lor de acces folosesc rute definite exclusiv in teste.

## Crearea conturilor de echipa

Endpoint: `POST /api/users`, disponibil doar pentru ADMIN, cu cookie JWT si CSRF valid.
Corpul este JSON, cu exact name, email, password si role:

```json
{
  "name": "Ana Popescu",
  "email": "ana@example.com",
  "password": "<parola initiala>",
  "role": "ACHIZITII"
}
```

Rolurile acceptate sunt ACHIZITII, DEPOZIT si CONTABILITATE, fara rol implicit.
Contul este creat activ. Acest endpoint nu creeaza administratori suplimentari.
Nu accepta is_active, password_hash, token_version sau un autor indicat de client.
Autorul auditului este administratorul autentificat.

Serviciul reverifica si blocheaza randul administratorului in tranzactia de scriere.
Valideaza datele, genereaza hashul bcrypt si salveaza contul impreuna cu evenimentul CREATE.
Un esec al auditului anuleaza si contul nou.
Un email deja folosit, inclusiv cu alta capitalizare sau spatii la capete, produce 409.
Contul existent ramane neschimbat.

La succes raspunde cu 201, mesajul si datele noului cont:
id, name, email, role si is_active. Nu returneaza parola, hashul sau un token nou.
Sesiunea administratorului ramane activa; colegul foloseste loginul obisnuit.
Datele invalide produc 400, lipsa sesiunii/CSRF produce 401,
rolul insuficient produce 403, iar o eroare a bazei sau auditului produce 503.
Corpul este limitat la 4096 de octeti; formatul necorespunzator produce 415 sau 413 pentru depasirea limitei.
Nu se trimit automat emailuri cu parola si nu exista inregistrare publica.

## Activarea si dezactivarea conturilor

Endpoint: `PATCH /api/users/<id>/status`, disponibil doar pentru ADMIN,
cu sesiune valida si antet CSRF corect.

```json
{
  "is_active": false,
  "reason": "Persoana nu mai lucreaza in echipa"
}
```

`is_active` trebuie sa fie boolean, iar motivul trebuie sa aiba intre 1 si 1000 de caractere.
Nu sunt acceptate alte campuri. Corpul este limitat la 4096 de octeti.
Raspunsul 200 contine mesajul si datele publice ale contului, inclusiv is_active.
Un cont necunoscut produce 404; datele invalide produc 400.

La fiecare schimbare reala de stare creste `token_version`.
Dezactivarea invalideaza astfel toate sesiunile contului.
Reactivarea permite un login nou, fara a reactiva tokenurile vechi.
Repetarea aceleiasi stari nu modifica versiunea si nu dubleaza auditul.
Contul si istoricul sau nu sunt sterse.

Serviciul reverifica administratorul si blocheaza randurile implicate.
O blocare de tranzactie comuna serializeaza schimbarile de stare,
astfel incat verificarile numarului de administratori activi sa nu se suprapuna.
Ultimul administrator activ nu poate fi dezactivat; cererea produce 409.
Un administrator se poate dezactiva pe sine doar daca ramane alt administrator activ.
Endpointul de creare a conturilor ramane limitat la cele trei echipe.

Starea, versiunea sesiunilor si auditul se salveaza impreuna.
Auditul pastreaza autorul, motivul si valorile de dinainte si de dupa,
cu actiunea ACTIVATE sau DEACTIVATE.
La esec raspundem cu 503, iar starea si versiunea raman neschimbate.
Schimbarea rolului nu este disponibila prin acest endpoint.

## Schimbarea rolului

Endpoint: `PATCH /api/users/<id>/role`, doar pentru ADMIN, cu sesiune si CSRF valide.

```json
{
  "role": "CONTABILITATE",
  "reason": "Transfer aprobat in echipa de contabilitate"
}
```

Rolurile permise sunt ADMIN, ACHIZITII, DEPOZIT si CONTABILITATE.
Motivul este obligatoriu si are intre 1 si 1000 de caractere.
Sunt acceptate doar role si reason; starea activa nu este modificata de aceasta operatie.
Raspunsul 200 include mesajul si datele publice actualizate ale contului.

La schimbarea reala a rolului creste versiunea sesiunilor si se salveaza ROLE_CHANGE
cu autorul, motivul, rolul vechi si rolul nou.
Contul trebuie sa se autentifice din nou pentru a folosi noile drepturi.
Repetarea aceluiasi rol nu invalideaza sesiunile si nu dubleaza auditul.
La esecul auditului sunt anulate si rolul si versiunea sesiunilor.

Protectia administratorilor foloseste aceeasi blocare ca activarea/dezactivarea.
Ultimul administrator activ nu poate primi un rol de echipa; cererea produce 409.
Un cont inactiv promovat la ADMIN ramane inactiv si nu permite retragerea rolului
ultimului administrator activ.
Transferul administrarii se poate face promovand mai intai alt cont activ,
apoi schimband rolul administratorului initial.
Promovarea este o operatie explicita, separata de crearea unui cont de echipa.

Lipsa sesiunii/CSRF produce 401, rolul insuficient produce 403,
contul necunoscut produce 404, datele invalide produc 400,
iar eroarea bazei sau auditului produce 503.
Corpul JSON este limitat la 4096 de octeti.

## Primul administrator

Cu PostgreSQL pornit si migrarile aplicate, din folderul `backend`:

```powershell
.\.venv\Scripts\python.exe -m flask --app app create-admin
```

Comanda cere numele, emailul, parola si confirmarea parolei.
Parola nu este afisata si nu exista o optiune `--password` care sa o lase in istoricul terminalului.
Contul primeste rolul ADMIN si starea activa.
Crearea contului si auditul se salveaza in aceeasi tranzactie.
Autorul auditului este procesul `initial_setup`, deoarece nu exista inca un utilizator autentificat.

Initializarea este refuzata daca exista deja orice cont ADMIN, inclusiv unul inactiv.
O blocare de tranzactie PostgreSQL serializeaza apelurile simultane ale acestei comenzi.
Un email folosit de alt cont este respins, fara promovarea acelui cont.
Listarea si crearea conturilor de echipa folosesc API-ul cu autentificare si permisiuni.
Schimbarea rolului foloseste endpointul separat de crearea contului si schimbarea starii.

## Audit

`AuditEvent` pastreaza cine, ce si cand, impreuna cu valorile relevante de dinainte si de dupa.
Autorul este fie un utilizator existent, fie un proces identificat, niciodata ambele.
Contul autor se pastreaza printr-o cheie externa; un cont cu istoric nu poate fi sters.
Referinta la document este generica, pentru a permite adaugarea comenzilor si facturilor ulterior.

Serviciul `record_audit()` adauga evenimentul in sesiunea curenta, fara `commit` sau `rollback` propriu.
Serviciul care modifica documentul trebuie sa salveze modificarea si auditul intr-o singura tranzactie.
Pentru documente noi se face `flush` in tranzactie pentru a obtine ID-ul inainte de audit.
Autorul va fi luat din identitatea autentificata, nu din corpul cererii trimise de utilizator.

Deocamdata sunt configurate doar operatiile pe conturi:
CREATE, UPDATE, ROLE_CHANGE, PASSWORD_CHANGE, ACTIVATE, DEACTIVATE, LOGIN si LOGOUT.
Operatia LOGIN_FAILED foloseste separat tipul authentication, cu email si remote_address permise.
Comanda `create-admin` inregistreaza automat auditul crearii.
POST /api/users inregistreaza auditul crearii cu identitatea administratorului autentificat.

Lista permisa pentru valorile contului: name, email, role si is_active.
Alte campuri si valorile imbricate sunt respinse; nu copiem requesturi sau obiecte complete.
Schimbarea parolei se noteaza ca actiune, fara parola sau hash.
Motivul este text liber: apelantul nu trebuie sa introduca parole sau alte secrete in el.

Evenimentele sunt protejate de modificarile ORM obisnuite.
Migrarea adauga si un trigger PostgreSQL care refuza UPDATE si DELETE.
Protectia nu impiedica un administrator al bazei sa modifice schema sau sa dezactiveze triggerul.
Testele PostgreSQL verifica triggerul, cheile externe si rollbackul tranzactiilor.
Nu expunem endpointuri de modificare sau stergere a auditului.

## Teste backend

Din folderul `backend`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Testele unitare verifica validarea datelor, parolele si serviciul de audit, fara baza de date.
Testele unitare ale auditului folosesc o sesiune simulata; verificarile PostgreSQL sunt separate.

Separat, testele PostgreSQL acopera baza, comanda locala, loginul, `/api/auth/me` si logoutul.
Aceste teste sunt omise implicit. Pentru rularea tuturor testelor, dupa pornirea bazei
si aplicarea migrarilor, din folderul `backend`, in PowerShell:

```powershell
$env:RUN_POSTGRES_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
Remove-Item Env:RUN_POSTGRES_TESTS
```

Se foloseste serverul PostgreSQL configurat in `.env`, cu drept de creare a schemelor de test.
Fiecare test creeaza o schema temporara separata si aplica migrarile reale acolo.
Schema si datele sunt anulate impreuna prin rollback la final;
commiturile din teste sunt izolate prin savepointuri.
Conturile si istoricul din schema aplicatiei nu sunt modificate.
Nu golim volumul si nu dezactivam triggerul de audit.

Verificarile includ salvarea si recitirea utilizatorilor si auditului, unicitatea emailului,
rolurile permise, autorul obligatoriu, blocarea UPDATE/DELETE asupra auditului
si anularea modificarii contului daca auditul sau operatia esueaza.
Comanda de initializare este verificata pentru parola ascunsa, confirmare,
refuzul unui al doilea administrator si rollback la esecul auditului.

Testele JWT verifica expirarea, semnatura alterata, cookie-urile si protectia CSRF
prin rute definite exclusiv in teste, fara folosirea conturilor reale.

Loginul este verificat pentru cookie, audit, cont inactiv, date incorecte,
validarea cererilor, origine, limitarea incercarilor si esecul auditului.

Testele `/me` acopera contul curent, starea inactiva, parola schimbata,
rolul actualizat, identitatea si versiunea invalide, expirarea si indisponibilitatea bazei.

Testele logoutului verifica revocarea, refuzul reutilizarii tokenului, CSRF,
stergerea cookie-urilor, izolarea sesiunilor, auditul unic si rollbackul la eroare.

Testele RBAC verifica matricea completa a rolurilor, drepturile actualizate,
refuzul escaladarii prin JWT si lista administrativa cu paginare.

Crearea conturilor este verificata pentru toate cele trei roluri, autorizare, CSRF,
validarea datelor, email duplicat, pastrarea sesiunii si rollback la esecul auditului.

Migrarea rolurilor este verificata pe conturi existente, inclusiv revenirea la schema anterioara
si pastrarea valorilor istorice din audit.

Testele starii conturilor verifica invalidarea sesiunilor, reactivarea cu login nou,
motivul si auditul, cererile repetate, rollbackul, accesul pe roluri
si protectia ultimului administrator, inclusiv blocarea intre conexiuni PostgreSQL.

Testele schimbarii rolului verifica toate cele patru roluri, invalidarea sesiunilor,
auditul si rollbackul, transferul administrarii, conturile inactive
si protectia comuna pentru schimbarea rolului si a starii.

## Catalogul de furnizori

Migrarea `0005_suppliers` adauga furnizorii. Crearea si auditul CREATE se salveaza
in aceeasi tranzactie. O eroare de audit anuleaza si furnizorul.

`POST /api/suppliers` necesita rolul ACHIZITII, sesiune si antetul CSRF.
Exemplu de corp JSON:

```json
{"name": "Furnizor exemplu", "tax_country": "RO", "tax_id": "12345", "email": "contact@example.com"}
```

Emailul este optional. Tara contine doua litere. Codul fiscal este pastrat cu litere
majuscule, fara spatii si fara prefixul tarii: RO12345 si 12345 pentru RO sunt aceeasi
identitate. Prefixele repetate sunt respinse. Perechea tara/cod fiscal este unica
si in PostgreSQL; un duplicat returneaza 409. Aceasta este normalizare interna,
nu verificare fiscala oficiala si nu confirma existenta firmei.

`GET /api/suppliers?page=1&per_page=20` este disponibil celor trei echipe.
Raspunsul contine suppliers, page, per_page si total. Limitele sunt page 1-1000000
si per_page 1-100; ordinea este dupa ID. Depozitul primeste doar id, name, is_active.
Achizitiile si contabilitatea primesc suplimentar tax_country, tax_id si email.
ADMIN nu are acces implicit la aceste operatii. Raspunsurile nu se memoreaza in cache.
`PATCH /api/suppliers/<id>` permite ACHIZITII sa modifice numele si/sau emailul,
cu sesiune, CSRF si motiv obligatoriu (1-1000 de caractere dupa eliminarea spatiilor marginale).
Tara si codul fiscal nu se modifica: o firma cu alta identitate se inregistreaza separat.
Exemplu:

```json
{"name": "Nume actualizat", "email": null, "reason": "Actualizare date de contact"}
```

`PATCH /api/suppliers/<id>/status` permite aceluiasi rol dezactivarea sau reactivarea:

```json
{"is_active": false, "reason": "Colaborare suspendata"}
```

Starea accepta doar valori JSON true/false. Furnizorii dezactivati raman in lista;
nu exista stergere. Inclusiv datele de contact ale unui furnizor inactiv pot fi corectate.
Modificarile sunt serializate prin blocarea randului in PostgreSQL si se salveaza
in aceeasi tranzactie cu auditul UPDATE, DEACTIVATE sau ACTIVATE, cu autor, motiv
si valorile vechi/noi. O cerere care nu schimba valorile normalizate nu adauga audit.
Un ID inexistent returneaza 404. Blocarea randului serializeaza salvarile;
daca doua persoane modifica acelasi camp, ultima salvare prevaleaza.
Documentele viitoare vor pastra separat datele istorice necesare.

Testele catalogului verifica accesul, proiectia pentru depozit, CSRF, duplicatele,
normalizarea, paginarea si anularea tranzactiei cand auditul esueaza.

## Catalogul de produse

Migrarea `0006_products` adauga produsele. `POST /api/products` necesita rolul
ACHIZITII, sesiune valida si antetul CSRF. Corpul trebuie sa contina exact:

```json
{"sku": "FILTRU-01", "name": "Filtru ulei", "unit": "BUC"}
```

SKU este codul intern unic al produsului. Eliminam spatiile marginale si folosim
majuscule: `filtru-01` si `FILTRU-01` identifica acelasi produs. Codul accepta
1-64 de caractere ASCII: litere, cifre, punct, cratima si underscore; primul
caracter trebuie sa fie litera sau cifra. Spatiile interioare nu sunt acceptate.
Un duplicat returneaza 409, inclusiv prin restrictia unica din PostgreSQL.
Numele are 1-200 de caractere, dupa eliminarea spatiilor marginale.

Unitatile acceptate sunt BUC (bucati), KG (kilograme), L (litri), M (metri),
M2 (metri patrati) si M3 (metri cubi). Unitatea este normalizata cu majuscule.
Fiecare produs are o singura unitate de baza; nu facem conversii automate.
Produsul se creeaza activ. Nu acceptam stoc sau stare din corpul cererii.

`GET /api/products?page=1&per_page=20` este disponibil pentru ACHIZITII,
DEPOZIT si CONTABILITATE. ADMIN nu primeste acces implicit.
Raspunsul contine products, page, per_page si total; fiecare produs contine
id, sku, name, unit si is_active. Ordinea este dupa ID. Limitele sunt
page 1-1000000 si per_page 1-100. Parametrii duplicati sau necunoscuti sunt respinsi.
Raspunsurile au Cache-Control: no-store.

Crearea produsului si auditul CREATE se salveaza in aceeasi tranzactie.
Auditul contine autorul si valorile initiale. Daca auditul esueaza, nu se salveaza
nici produsul. Testele folosesc scheme PostgreSQL izolate si verifica rolurile,
CSRF, normalizarea, duplicatele, paginarea, restrictiile bazei si rollbackul.

`PATCH /api/products/<id>` permite ACHIZITII sa modifice numele, cu CSRF si motiv:

```json
{"name": "Filtru ulei actualizat", "reason": "Corectie denumire"}
```

`PATCH /api/products/<id>/status` permite dezactivarea sau reactivarea:

```json
{"is_active": false, "reason": "Produs retras din utilizare"}
```

Motivul trebuie sa aiba 1-1000 de caractere dupa eliminarea spatiilor marginale.
Starea accepta doar true/false. SKU si unitatea nu se modifica pentru a pastra
identitatea si baza de calcul a cantitatilor. Produsele inactive raman in lista;
nu exista stergere. Numele poate fi corectat inclusiv pentru un produs inactiv.

Salvarea blocheaza randul produsului in PostgreSQL. Auditul UPDATE, ACTIVATE sau
DEACTIVATE contine autorul, motivul si valorile vechi/noi si se salveaza in aceeasi
tranzactie. O eroare anuleaza intreaga operatie. Cererile fara schimbari reale
nu adauga audit. Daca doua persoane modifica acelasi nume, ultima salvare prevaleaza.
Documentele viitoare vor pastra separat descrierile istorice necesare.

Stocul se calculeaza din miscarile de marfa. Sunt implementate intrarile din
receptii confirmate; soldul initial si celelalte tipuri de miscare urmeaza separat.

## Comenzi catre furnizori: ciorne

Migrarea `0007_purchase_orders` adauga comenzile si pozitiile lor.
`POST /api/purchase-orders` necesita ACHIZITII, sesiune valida si CSRF.

```json
{
  "supplier_id": 1,
  "currency": "RON",
  "items": [
    {
      "product_id": 1,
      "quantity": "5.000",
      "unit_price": "12.5000",
      "vat_rate": "0.00",
      "expected_date": "2026-11-10"
    }
  ]
}
```

ID-urile trebuie sa existe in catalog. Furnizorul si produsele trebuie sa fie active.
Codul intern este generat de PostgreSQL, de forma CA-1, pe baza ID-ului; numerotarea
poate avea goluri dupa operatii anulate. Moneda accepta exact RON sau EUR.
Comanda se creeaza doar DRAFT, cu version 1. Autorul si responsabilul sunt
utilizatorul autentificat; nu se pot trimite din client.

Ciorna poate avea 0-100 de pozitii. Acelasi produs poate aparea pe pozitii distincte,
de exemplu cu termene diferite. Fiecare pozitie primeste automat numarul de ordine,
descrierea si unitatea din catalog. Aceste valori raman pastrate pe document chiar
daca numele produsului se modifica ulterior.

Cantitatile, preturile si TVA se trimit ca texte zecimale, cu punct, fara exponent.
Cantitatea este pozitiva, cu maximum 3 zecimale si sub 10^15; pretul este nenegativ,
cu maximum 4 zecimale si sub 10^14. TVA este intre 0 si 100, cu maximum 2 zecimale.
Cota TVA este introdusa de utilizator; nu este calculata sau verificata fiscal.
Nu rotunjim in tacere valori cu prea multe zecimale si nu folosim float pentru bani.
Raspunsurile pastreaza zecimalele ca texte. Termenul este o data valida YYYY-MM-DD,
inclusiv o data trecuta pentru inregistrarea comenzilor istorice.

Furnizorul si produsele sunt blocate la creare pentru a verifica starea si a salva
descrierile in aceeasi tranzactie. Antetul, toate pozitiile si auditul lor CREATE
se salveaza impreuna. Auditul antetului refera comanda; fiecare pozitie are audit
separat, legat prin purchase_order_id. Nu sunt trimise emailuri in acest pas.

`GET /api/purchase-orders?page=1&per_page=20` returneaza orders, page, per_page si total.
Lista contine antetele, fara pozitii. Limite: page 1-1000000 si per_page 1-100.
Ordinea este dupa ID; parametrii duplicati/necunoscuti sunt respinsi.
`GET /api/purchase-orders/<id>` returneaza antetul si pozitiile ordonate.
ACHIZITII vede toate comenzile. DEPOZIT si CONTABILITATE vad numai comenzi cu
starea CONFIRMED sau CLOSED si data confirmarii completata. Ciornele raman ascunse.
Pentru un document ascuns, detaliul returneaza 404, iar totalul listei il exclude.
ADMIN nu are acces implicit la aceste operatii.
Raspunsurile au Cache-Control: no-store; un ID inexistent returneaza 404.

Nu sunt implementate inca anularea sau inchiderea comenzilor.
Ciornele nu modifica stocul si nu permit aprobarea vreunei facturi.

### Editarea ciornelor

`PATCH /api/purchase-orders/<id>` necesita ACHIZITII, sesiune si CSRF.
Trimite toate campurile editabile si lista completa de pozitii, plus versiunea
primita la citire si motivul (1-1000 de caractere dupa eliminarea spatiilor marginale):

```json
{
  "supplier_id": 1,
  "currency": "EUR",
  "version": 1,
  "reason": "Actualizare cantitate si termen",
  "items": [
    {
      "id": 1,
      "product_id": 1,
      "quantity": "8.000",
      "unit_price": "12.5000",
      "vat_rate": "0.00",
      "expected_date": "2026-11-15"
    }
  ]
}
```

ID-urile din exemplu trebuie inlocuite cu cele primite din API. O pozitie existenta
trebuie trimisa cu id-ul ei; o pozitie noua se trimite fara id. O pozitie existenta
omisa din lista este eliminata din ciorna, cu audit DELETE. Lista goala elimina
toate pozitiile. Ordinea listei stabileste numerotarea pozitiilor.

Nu se pot folosi ID-uri ale altei comenzi sau acelasi ID de doua ori. Produsul unei
pozitii existente nu se schimba; pentru alt produs se elimina pozitia si se adauga
una noua. Cantitatea, pretul, TVA si termenul sunt editabile, cu validarile de la creare.
Pozitiile existente pastreaza descrierea si unitatea istorice; cele noi le preiau
din catalog. Furnizorul si toate produsele trimise trebuie sa fie active la salvare.
Se poate elimina o pozitie cu produs devenit inactiv. Numarul comenzii, autorul,
responsabilul si starea nu sunt editabile prin aceasta ruta.

Numai DRAFT se poate edita; alte stari returneaza 409. Comanda este blocata in
PostgreSQL la salvare. O versiune veche returneaza 409 si necesita recitirea comenzii,
fara suprascriere automata. O modificare reala incrementeaza version; o cerere fara
schimbari reale nu incrementeaza versiunea si nu adauga audit.

Auditul antetului si al pozitiilor modificate/adaugate/eliminate contine autorul,
motivul si valorile relevante vechi/noi. Toata salvarea este o singura tranzactie:
orice eroare de audit anuleaza inclusiv modificarile, stergerile si versiunea.
Nu este necesara o migrare noua pentru editare.

### Confirmarea comenzilor

`POST /api/purchase-orders/<id>/confirm` necesita ACHIZITII, sesiune si CSRF.
Trimite doar versiunea curenta, primita la citirea comenzii:

```json
{"version": 1}
```

Comanda trebuie sa fie DRAFT si sa aiba cel putin o pozitie. Revalidam furnizorul
si produsele active, cantitatile, preturile, TVA, termenele si unitatile produselor.
Termenele trecute sunt permise, pentru inregistrarea comenzilor istorice.
Descrierile existente sunt pastrate. O versiune veche sau o stare diferita de DRAFT
returneaza 409; datele incomplete sau intrarile din catalog dezactivate returneaza 400.

Confirmarea blocheaza comanda la salvare, o trece in CONFIRMED, incrementeaza
versiunea si salveaza confirmed_at in UTC. Auditul CONFIRM pastreaza autorul,
starea, versiunea si data veche/noua, in aceeasi tranzactie. O eroare de audit
anuleaza confirmarea. Repetarea cererii returneaza 409, fara evenimente duplicate.
Editarea prin ruta de ciorne este blocata dupa confirmare.

Raspunsurile includ confirmed_at (null pentru ciorne, data ISO 8601 pentru confirmate).
DEPOZIT primeste in antet doar id, number, supplier_id, status, version, confirmed_at;
pozitiile contin id, line_number, product_id, description, unit, quantity, expected_date.
Preturile, TVA si moneda sunt excluse din interogarile SQL pentru acest rol.
CONTABILITATE primeste suplimentar moneda, responsabilul, autorul si preturile/TVA.
Dezactivarea ulterioara a furnizorului sau produsului nu ascunde documentele confirmate.

Confirmarea nu trimite email furnizorului si nu modifica stocul.
Nu este necesara o migrare noua; folosim campurile existente la `0007_purchase_orders`.

Ultima verificare: 452 de teste trecute; schema ramane la `0007_purchase_orders`.

## Receptii de marfa: ciorne

Migrarea `0008_receipts` adauga receptiile si pozitiile lor.
`POST /api/receipts` necesita rolul DEPOZIT, sesiune si CSRF. Exemplu:

```json
{
  "purchase_order_id": 1,
  "delivery_reference": "AVIZ-123",
  "received_at": "2026-10-20T10:30:00+03:00",
  "items": [
    {"purchase_order_item_id": 1, "received_quantity": "3.125"}
  ]
}
```

ID-urile se iau din comanda consultata de depozit. Comanda trebuie sa existe,
sa fie CONFIRMED si sa aiba data confirmarii. Alte stari returneaza 409.
Furnizorul se preia din comanda; produsul, descrierea si unitatea se preiau din
pozitia comenzii, fara consultarea preturilor. Catalogul dezactivat ulterior nu
impiedica inregistrarea faptului ca marfa a sosit.

Referinta documentului de livrare are 1-120 de caractere dupa eliminarea spatiilor
marginale. Nu este unica: aceeasi referinta poate aparea in mai multe transe.
Data necesita ora si fus orar explicit (Z sau offset); se pastreaza in UTC.
Nu impunem in acest pas o limita fata de data curenta; data introdusa trebuie verificata de operator.

Receptia necesita 1-100 de pozitii, toate din aceeasi comanda. O pozitie de comanda
poate aparea o singura data in aceeasi receptie. Pozitii omise sunt permise pentru
livrarile partiale. Se pot inregistra mai multe receptii pentru aceeasi comanda.
Cantitatea sosita este un text zecimal pozitiv, cu maximum 3 zecimale si sub 10^15.
Surplusul fata de comanda este permis la inregistrare, ca fapt fizic, fara acceptare automata.

Starea initiala este DRAFT, cu version 1 si numar generat REC-<id>. Autorul este
utilizatorul autentificat. Cantitatea acceptata si cea respinsa sunt initial zero;
toata cantitatea sosita este in asteptare. API-ul nu accepta cantitati acceptate,
furnizor, produs, autor sau stare trimise separat de client.
PostgreSQL verifica inclusiv egalitatea: sosita = acceptata + respinsa + in asteptare.

Comanda, pozitiile ei si contul operatorului sunt blocate in tranzactia de creare.
Receptia, pozitiile si auditul CREATE se salveaza impreuna. O eroare de audit
anuleaza tot. Nu se modifica stocul, cantitatile comandate sau eligibilitatea facturilor.

`GET /api/receipts?page=1&per_page=20` returneaza receipts, page, per_page si total,
cu antetele ordonate dupa ID. Limite: page 1-1000000 si per_page 1-100.
`GET /api/receipts/<id>` returneaza antetul si pozitiile, fara preturi.
DEPOZIT vede toate receptiile. ACHIZITII si CONTABILITATE vad numai receptiile
CONFIRMED, cu data si autorul confirmarii completate. Ciornele si receptiile anulate
nu sunt vizibile acestor doua echipe; lista si totalul paginarii le exclud,
iar accesarea directa returneaza 404. ADMIN nu are acces implicit.
Raspunsurile au Cache-Control: no-store. Un ID inexistent returneaza 404.

Nu sunt implementate inca anularea receptiilor sau marfa fara legatura la comanda.
Repetarea crearii produce o noua
ciorna; nu exista inca o cheie de idempotenta pentru aceasta operatie.

Ultima verificare: 493 de teste trecute, migrari la `0008_receipts`,
fara diferente intre modele si schema PostgreSQL.

### Corectarea ciornei receptiei

`PATCH /api/receipts/<id>` necesita DEPOZIT, sesiune valida si CSRF.
Trimite referinta documentului, data cu fus orar, lista completa a pozitiilor existente,
versiunea citita si motivul obligatoriu (1-1000 de caractere dupa eliminarea spatiilor marginale):

```json
{
  "version": 1,
  "reason": "Corectie dupa renumarare",
  "delivery_reference": "AVIZ-123",
  "received_at": "2026-10-20T10:30:00+03:00",
  "items": [
    {"id": 1, "received_quantity": "4.250"}
  ]
}
```

ID-urile se iau din detaliul receptiei. Fiecare pozitie existenta trebuie sa apara
exact o data; se foloseste ID-ul pozitiei de receptie, nu al pozitiei de comanda.
Cantitatea este pozitiva, cu maximum 3 zecimale si sub 10^15. Cantitatea in asteptare
se actualizeaza la aceeasi valoare; acceptata si respinsa raman zero.
Ordinea pozitiilor nu se modifica prin aceasta operatie.

Acest pas permite corectarea referintei, datei si cantitatilor. Nu permite adaugarea,
eliminarea sau schimbarea produsului/legaturii unei pozitii. Furnizorul, numarul,
autorul si starea nu se trimit din client. Cantitatile deja clasificate sunt protejate
de suprascriere; vor necesita operatii separate de corectie.

Receptia trebuie sa fie DRAFT, fara data sau autor de confirmare. O alta stare sau
o versiune veche returneaza 409. Un ID inexistent returneaza 404. Salvarea blocheaza
randul receptiei, pastreaza ID-urile si descrierile si incrementeaza versiunea doar
pentru schimbari reale. O cerere echivalenta dupa normalizare nu adauga audit.
Corectarea cantitatilor nu necesita reactivarea produsului sau furnizorului si nu
modifica comanda sursa ori stocul.

Auditul UPDATE al antetului si al pozitiilor modificate pastreaza autorul, motivul
si valorile vechi/noi. Totul se salveaza intr-o singura tranzactie; o eroare de audit
anuleaza inclusiv cantitatile si versiunea. Nu este necesara o migrare noua.

Verificarea acestei modificari: 91 de teste pentru receptii si audit trecute.
Ultima suita completa, inaintea editarii receptiilor: 493 de teste trecute.

### Confirmarea receptiei si intrarea in stoc

Migrarea `0009_stock_movements` adauga registrul de intrari de stoc.
`POST /api/receipts/<id>/confirm` necesita DEPOZIT, sesiune, CSRF, versiune curenta,
motiv obligatoriu (1-1000 de caractere) si clasificarea tuturor pozitiilor:

```json
{
  "version": 1,
  "reason": "Verificare cantitativa la primire",
  "items": [
    {
      "id": 1,
      "accepted_quantity": "2.000",
      "rejected_quantity": "1.000",
      "pending_quantity": "0.125"
    }
  ]
}
```

In exemplu, cantitatea sosita trebuie sa fie 3.125. ID-ul este al pozitiei de
receptie. Toate cantitatile sunt texte zecimale nenegative, cu maximum 3 zecimale,
iar suma acceptata + respinsa + in asteptare trebuie sa fie exact cantitatea sosita.
Pozitiile lipsa, duplicate sau ale altei receptii sunt respinse cu 400.
Recepția trebuie sa fie DRAFT, neconfirmata, cu cantitatile initiale in asteptare.
Versiunea veche sau repetarea confirmarii returneaza 409, fara dublarea intrarilor.

Acceptarea pozitiva necesita o comanda CONFIRMED, deschisa, furnizor compatibil,
acelasi produs si aceeasi unitate, iar produsul trebuie sa fie activ.
Nu este necesara reactivarea furnizorului pentru o livrare dintr-o comanda deja confirmata.
Cantitatea acceptata cumulata in toate receptiile confirmate nu poate depasi
cantitatea comandata pe pozitia respectiva. Surplusul poate ramane in asteptare
sau poate fi respins. Se poate confirma o receptie integral respinsa/in asteptare,
fara miscare de stoc; restrictiile comenzii se aplica acceptarii pozitive.

Salvarea blocheaza receptia, comenzile, pozitiile de comanda si produsele implicate,
in ordine stabila. Acceptarea cumulata se verifica dupa obtinerea blocarilor.
Testul cu doi operatori si conexiuni simultane verifica faptul ca acelasi rest
nu poate fi acceptat de doua ori.

Confirmarea completeaza confirmed_at in UTC si confirmed_by_id, incrementeaza
versiunea si blocheaza editarea prin ruta de ciorne. Fiecare cantitate acceptata
pozitiva genereaza o miscare RECEIPT, cu autor, motiv si cheie de operatie unica.
Cantitatile respinse sau in asteptare nu intra in stoc.
Antetul, clasificarea, miscarile si auditul CONFIRM/UPDATE/CREATE se salveaza
intr-o singura tranzactie. Orice eroare anuleaza toate aceste modificari.

Miscarile sunt protejate impotriva UPDATE si DELETE atat prin ORM, cat si prin
trigger PostgreSQL. Administratorul bazei poate interveni asupra protectiilor;
acestea protejeaza fluxul normal al aplicatiei. Corectiile vor folosi miscari separate.

`GET /api/stock?page=1&per_page=20` permite celor trei echipe consultarea cantitatilor.
ADMIN nu are acces implicit. Raspunsul contine stock, page, per_page si total;
fiecare produs contine id, sku, name, unit, is_active si quantity ca text cu 3 zecimale.
Sunt incluse si produsele inactive sau fara intrari (cantitate zero). Ordinea este
dupa ID, page este 1-1000000, per_page este 1-100, iar parametrii necunoscuti sau
duplicati sunt respinsi. Raspunsurile au Cache-Control: no-store.
Soldul se calculeaza prin suma miscarilor, fara un sold editabil separat.

In acest pas nu exista iesiri, retururi, ajustari, anulare de receptie sau acceptare
ulterioara a cantitatilor in asteptare. Registrul permite momentan numai RECEIPT.
Consultarea receptiilor confirmate este disponibila si pentru ACHIZITII si
CONTABILITATE. Nu exista inca verificarea facturilor.

Ultima verificare: 557 de teste trecute, inclusiv confirmarea simultana de catre
doi operatori. Migrari la `0009_stock_movements`, fara diferente intre modele
si schema PostgreSQL.

### Consultarea receptiilor intre echipe

`GET /api/receipts` si `GET /api/receipts/<id>` folosesc rolul curent verificat
in baza de date. DEPOZIT pastreaza accesul la toate receptiile. ACHIZITII si
CONTABILITATE primesc doar documentele confirmate complet (stare CONFIRMED,
confirmed_at si confirmed_by_id nenule). Filtrarea se aplica in interogarea SQL,
inclusiv totalului listei; nu este doar o ascundere in interfata.

Antetul contine numarul, furnizorul, documentul de livrare, datele receptiei si
confirmarii, autorii, starea si versiunea. Pozitiile contin produsul, descrierea,
unitatea, legatura la comanda si cantitatile sosite/acceptate/respinse/in asteptare.
Nu exista preturi sau date de autentificare in aceste raspunsuri.
O receptie confirmata poate avea marfa in asteptare sau respinsa; confirmarea nu
inseamna acceptarea integrala si nu aproba plata vreunei facturi.

Celelalte echipe au doar drept de consultare. Crearea, corectarea ciornei si
confirmarea raman disponibile exclusiv pentru DEPOZIT, cu sesiune si CSRF.
Nu este necesara o migrare noua si citirea nu modifica stocul sau auditul.

Verificarea acestei modificari: 112 teste pentru receptii trecute, inclusiv
toate rolurile, totalul filtrat, accesul direct la ciorne si documentele din cache.

### Restul de livrat pe comanda

`GET /api/purchase-orders/<id>/delivery` returneaza situatia cantitativa pe pozitii.
Accesul este identic detaliului comenzii: ACHIZITII vede inclusiv ciornele;
DEPOZIT si CONTABILITATE vad numai comenzile confirmate/inchise cu data confirmarii.
ADMIN nu primeste acces implicit. Un document ascuns sau inexistent returneaza 404.

Raspunsul contine delivery, cu id, number, status si items. Fiecare pozitie contine
id, line_number, product_id, description, unit, quantity, expected_date,
accepted_quantity, remaining_quantity si delivery_status. Nu include preturi sau TVA.
Cantitatile sunt texte cu 3 zecimale.

Formula este remaining_quantity = quantity - accepted_quantity. Cantitatea acceptata
este suma cantitatilor acceptate din receptiile CONFIRMED, legate la aceeasi pozitie
de comanda. Ciornele, cantitatile respinse si cele in asteptare nu reduc restul.
Pozitiile cu acelasi produs se calculeaza separat, inclusiv intre comenzi diferite.

delivery_status este NOT_RECEIVED cand nu exista acceptari, PARTIAL cand exista
acceptari si rest pozitiv, COMPLETE cand restul este zero. Aceste valori descriu
pozitia, separat de starea documentului DRAFT/CONFIRMED/CLOSED/CANCELLED.
In ciorna, calculul este informativ; nu produce obligatii de receptie.

Restul se calculeaza la citire, fara o coloana editabila in baza de date si fara
migrare noua. Ruta nu modifica auditul, stocul sau versiunea comenzii si foloseste
Cache-Control: no-store. In acest pas nu exista inchiderea explicita a restului,
retururi sau corectii; cand le implementam, vom extinde formula cu efectele lor.

Verificarea acestei modificari: 210 teste pentru comenzi si receptii trecute,
inclusiv livrari in transe, precizie zecimala, separarea pozitiilor si accesul pe roluri.

### Pozitii de comanda intarziate

`GET /api/purchase-orders/overdue?page=1&per_page=20` este disponibil pentru
ACHIZITII, DEPOZIT si CONTABILITATE. ADMIN nu primeste acces implicit.
O pozitie este intarziata doar daca termenul este inaintea zilei curente din
Europe/Bucharest si restul de livrat este pozitiv. Termenele de azi nu sunt
intarziate. Zilele de intarziere sunt zile calendaristice, nu zile lucratoare.

Sunt incluse doar comenzile CONFIRMED cu data confirmarii completata. Ciornele,
comenzile anulate/inchise si pozitiile complet acceptate sunt excluse.
Livrarile partial acceptate raman vizibile pentru restul deschis.
Marfa respinsa/in asteptare si receptiile neconfirmate nu reduc restul.

Raspunsul contine items, page, per_page, total, as_of (data de referinta) si
timezone (Europe/Bucharest). Fiecare pozitie contine order_id, order_number,
supplier_id, id (ID-ul pozitiei), line_number, product_id, description, unit,
quantity, expected_date, accepted_quantity, remaining_quantity si days_overdue.
Cantitatile sunt texte cu 3 zecimale; nu sunt incluse preturi sau TVA.

Ordinea este dupa termen crescator, apoi comanda si numarul pozitiei. Paginarea
se aplica dupa filtrarea intarzierilor: page 1-1000000 si per_page 1-100.
Parametrii duplicati/necunoscuti, inclusiv o data de referinta trimisa de client,
sunt respinsi cu 400. Ora locala se calculeaza in PostgreSQL cu Europe/Bucharest,
inclusiv regulile de vara/iarna; nu folosim fusul orar implicit al sistemului.

Aceeasi agregare a acceptarilor confirmate este folosita atat pentru restul
comenzii, cat si pentru intarzieri. Nu salvam separat un indicator de intarziere,
nu modificam documentele/auditul/stocul si nu trimitem emailuri in acest pas.
Raspunsurile au Cache-Control: no-store. Nu este necesara o migrare noua.

Verificarea intarzierilor: 226 de teste pentru comenzi si receptii trecute,
inclusiv limita dintre zile, fusul orar vara/iarna, livrari partiale si paginare.

### Previzualizarea sumarului email de intarzieri

Din directorul backend:

```powershell
.\.venv\Scripts\python.exe -m flask --app app preview-overdue-emails
```

Comanda pregateste mesajele pentru responsabilii din ACHIZITII, fara trimitere.
Afiseaza destinatarul, subiectul, continutul si numarul de mesaje. Este o comanda
pentru operatorul serverului, nu o ruta HTTP disponibila utilizatorilor aplicatiei.
Nu necesita setari SMTP si nu modifica documentele, stocul sau auditul.

Destinatarul este owner_id al comenzii, numai daca acel cont este activ si are
in continuare rolul ACHIZITII. Nu exista destinatari impliciti ADMIN sau din alte
echipe. O persoana primeste un singur mesaj cu toate pozitiile sale intarziate,
ordonate dupa termen, comanda si numarul pozitiei. Daca nu are intarzieri, nu
pregatim un mesaj gol. Conturile neeligibile sunt excluse, iar CLI afiseaza
numarul pozitiilor fara responsabil eligibil, pentru clarificare.

Serviciul foloseste aceeasi interogare de intarzieri ca API-ul, cu aceeasi data
Europe/Bucharest. Include toate pozitiile eligibile, fara limita paginii API.
Corpul este text simplu, generat din app/templates/emails/overdue_digest.txt,
si contine numarul comenzii, pozitia, descrierea, restul, unitatea, termenul
si zilele de intarziere. Nu include preturi, TVA, parole sau tokenuri.

Generarea si previzualizarea sunt disponibile separat de trimiterea SMTP locala
de test descrisa mai jos. Jurnalul persistent si deduplicarea zilnica sunt implementate.
SMTP extern nu este implementat. Programarea zilnica locala si reluarile programate
pentru erori certe sunt implementate prin workerul CLI descris mai jos.
La preluarea fiecarui mesaj este reverificata eligibilitatea
destinatarului. Inainte de activarea in utilizare reala se valideaza destinatarii
si frecventa sumarului cu firma.

Verificarea acestui pas: 242 de teste pentru notificari, comenzi, receptii si
comenzile CLI relevante trecute.

### Testarea emailurilor in Mailpit local

Porneste serviciul din radacina proiectului:

```powershell
docker compose up -d mailpit
```

Deschide inboxul de test la http://localhost:8025. Mailpit este fixat la versiunea
v1.31.6. Porturile SMTP 1025 si UI 8025 sunt publicate numai pe 127.0.0.1.
MAILPIT_SMTP_PORT si MAILPIT_UI_PORT sunt optionale in .env si au aceste valori implicite.
Nu sunt necesare credentiale SMTP pentru acest server local de test.

Din backend poti trimite un mesaj demonstrativ cu date sintetice, fara a crea
utilizatori sau documente in baza de date:

```powershell
.\.venv\Scripts\python.exe -m flask --app app send-test-email
```

Mesajul are subiectul [TEST] Ruris, destinatarul achizitii@example.com si un rest
demonstrativ de 7.000 BUC cu termenul de ieri, dupa data Europe/Bucharest.
Foloseste acelasi sablon ca sumarul real. Necesita PostgreSQL pentru calculul
datei de referinta. Mesajul este capturat local, nu trimis la casuta destinatarului.

Pentru sumarele calculate din comenzile existente:

```powershell
.\.venv\Scripts\python.exe -m flask --app app send-overdue-emails-local
```

Transportul foloseste smtplib si EmailMessage din biblioteca standard Python.
Se conecteaza exclusiv la 127.0.0.1, pe MAILPIT_SMTP_PORT, cu timeout de 5 secunde.
Nu configureaza relay SMTP, autentificare sau TLS; este exclusiv pentru testul local
cu Flask rulat pe calculator. Containerizarea ulterioara a backendului va necesita
adaptarea adresei serviciului. Erorile conexiunii nu expun detalii interne.

CLI raporteaza numarul mesajelor acceptate de Mailpit si starile pentru ziua curenta.
Sumarele au acum jurnal persistent si deduplicare zilnica. Mesajele SENT, SENDING
si UNKNOWN nu se retrimit la repetarea comenzii. Trimiterea sumarurilor adauga audit,
fara sa modifice documentele sau stocul. Mesajul demonstrativ send-test-email ramane
separat, poate fi repetat si nu foloseste jurnalul sumarurilor.

Testul de integrare SMTP se activeaza explicit, cu Mailpit si PostgreSQL pornite:

```powershell
$env:RUN_POSTGRES_TESTS='1'
$env:RUN_MAILPIT_TESTS='1'
.\.venv\Scripts\python.exe -m pytest tests/test_mail.py tests/test_notifications.py tests/test_create_admin.py tests/test_jwt_config.py -q -p no:cacheprovider
```

Testul foloseste date intr-o schema PostgreSQL izolata si verifica mesajul capturat
prin API-ul Mailpit, cu destinatar unic de test. Nu sterge mesajele deja existente
in inboxul local. Ultima verificare: 46 de teste trecute, inclusiv SMTP real local.

Documentatie: [Mailpit Docker](https://mailpit.axllent.org/docs/install/docker/)
si [API Mailpit](https://mailpit.axllent.org/docs/api-v1/).

### Jurnalul trimiterilor si prevenirea duplicatelor

Migrarea `0010_email_delivery` adauga `email_outbox` si `email_attempts`.
Comanda `send-overdue-emails-local` pregateste in PostgreSQL un singur sumar
OVERDUE/LOCAL_MAILPIT pentru fiecare responsabil si zi Europe/Bucharest.
Unicitatea este impusa in baza de date, inclusiv intre procese simultane.
Mesajul este o copie a sumarului la pregatire: destinatar, subiect, continut si hash.

| Stare | Semnificatie | Comportament la o noua rulare |
| --- | --- | --- |
| PENDING | Pregatit, fara trimitere inceputa | Poate fi preluat |
| SENDING | Incercarea a fost salvata inainte de SMTP | Nu se retrimite automat |
| SENT | Serverul SMTP a confirmat acceptarea | Nu se retrimite in aceeasi zi |
| FAILED | Eroare inaintea trimiterii sau refuz SMTP explicit | Poate fi reluat dupa next_attempt_at, maximum 3 incercari totale |
| UNKNOWN | Conexiune intrerupta dupa inceperea transmiterii | Nu se retrimite automat |
| SKIPPED | Destinatar sau continut schimbat/ineligibil | Nu se trimite copia veche |

Fiecare incercare are numar, moment de inceput/finalizare si cod de eroare controlat.
Nu salvam exceptii brute, parole sau credentiale SMTP in jurnal. Corpul mesajului
este pastrat in outbox, pentru trasabilitatea datelor pregatite.
Auditul ENQUEUE/START/SENT/FAILED/UNKNOWN/SKIP pastreaza procesul autor si starile,
fara a copia corpul emailului. Schimbarea starii si auditul ei sunt atomice in PostgreSQL.

Preluarea foloseste blocare de rand cu SKIP LOCKED. Starea SENDING si incercarea
sunt salvate inainte de contactarea serverului SMTP. Alte procese nu preiau aceeasi
trimitere. Un test cu doua conexiuni simultane verifica atat unicitatea pregatirii,
cat si preluarea de catre un singur proces.

Inainte de START verificam contul activ, rolul ACHIZITII, emailul curent si hash-ul
sumarului regenerat pentru rularea curenta. Un sumar modificat intre pregatire si
preluare devine SKIPPED; nu inlocuim automat mesajul zilei cu alt continut. O zi noua
permite un sumar nou, calculat din datele actuale. Mesajele fara intarzieri nu se pregatesc.

SMTP si PostgreSQL nu formeaza o singura tranzactie. Daca serverul accepta mesajul,
dar salvarea rezultatului esueaza, randul ramane SENDING. SENDING si UNKNOWN necesita
verificare manuala in Mailpit; nu exista inca o comanda de resetare/retrimitere fortata.
Un Message-ID stabil ajuta verificarea, dar nu garanteaza deduplicarea de catre SMTP.
Protectia previne retrimiterea automata a rezultatelor neclare; nu promite livrare
exact o data pentru orice defect de retea sau oprire a procesului.

Din backend, pentru ultimele inregistrari:

```powershell
.\.venv\Scripts\python.exe -m flask --app app list-email-deliveries --limit 20
```

Limita este 1-100. CLI afiseaza ID-ul, ziua, responsabilul, starea, numarul de
incercari si ultimul cod de eroare. Nu afiseaza corpul mesajului. Inregistrarile
se pastreaza si dupa repornirea aplicatiei, in volumul PostgreSQL.
Comanda nu este o ruta HTTP; accesul este cel al operatorului serverului.

Procesarea curenta priveste ziua curenta, nu reia mesaje din zile anterioare.
Exista un worker zilnic local si un interval fix persistent intre reincercari.
Nu exista backoff exponential, SMTP extern sau tratarea facturilor blocate.

Ultima verificare: 625 de teste trecute, inclusiv pregatirea/preluarea concurenta,
repetarea trimiterii SMTP reale fara duplicate si erori dupa acceptarea SMTP.
Migrari la `0010_email_delivery`, fara diferente intre modele si schema PostgreSQL.

### Programarea zilnica a notificarilor locale

Migrarea `0011_email_retry_schedule` adauga next_attempt_at in jurnal.
Din backend, intr-un terminal separat:

```powershell
.\.venv\Scripts\python.exe -m flask --app app run-notification-worker
```

Procesul trebuie sa ramana pornit. Nu porneste automat odata cu serverul Flask si
nu se instaleaza ca serviciu Windows. Ctrl+C il opreste. Pentru productie/deploy
va trebui rulat sub un manager de procese sau intr-un container dedicat.

Implicit, sumarul zilnic este procesat la 08:00 Europe/Bucharest, cu verificare
la fiecare 60 de secunde. Ora se calculeaza in PostgreSQL, inclusiv vara/iarna.
Configuratia optionala din .env este:

```dotenv
EMAIL_DAILY_TIME=08:00
EMAIL_RETRY_SECONDS=300
```

Ora necesita format HH:MM. Intervalul reincercarilor este intre 60 si 3600 de secunde.
La schimbarea setarilor se reporneste workerul. `--poll-seconds` permite o verificare
la 1-60 de secunde, fara a modifica ora zilnica sau intervalul de reincercare.

Pentru o singura verificare, fara bucla si fara asteptare:

```powershell
.\.venv\Scripts\python.exe -m flask --app app run-notification-worker --once
```

`--once` respecta ora configurata, nu forteaza trimiterea inaintea ei.
Daca workerul porneste dupa ora programata, proceseaza ziua curenta; nu genereaza
retroactiv sumaruri pentru zilele in care a fost oprit. Dupa finalizarea zilei,
evita alte rulari in acelasi proces pana in ziua urmatoare. La repornire poate
reverifica ziua curenta; unicitatea din outbox previne retrimiterea mesajelor SENT.
Intarzierile noi aparute dupa finalizarea sumarului sunt incluse in urmatorul sumar zilnic.

La o eroare SMTP certa, workerul salveaza in PostgreSQL next_attempt_at (UTC),
implicit peste 5 minute. Pana atunci nu contacteaza din nou SMTP, inclusiv dupa
repornire sau o rulare manuala. Maximum 3 incercari totale per mesaj si zi.
Comanda manuala send-overdue-emails-local pastreaza comportamentul imediat pentru
erorile produse de ea, dar respecta orice next_attempt_at deja programat.
SENDING si UNKNOWN nu sunt reluate automat. Modificarile momentului de reincercare
sunt incluse in audit, iar list-email-deliveries afiseaza termenul in UTC.

Erorile PostgreSQL sunt raportate fara detalii de conexiune, iar workerul reincearca
verificarea la urmatorul interval. Tranzactia de citire este inchisa intre verificari.
Deduplicarea si blocarile din jurnal raman valabile daca pornesc mai multi workeri.
SMTP este in continuare exclusiv Mailpit local; acest pas nu trimite emailuri externe.

Workerul a fost verificat efectiv cu --once. Nu este lasat pornit permanent in fundal.

Ultima verificare: 650 de teste trecute, inclusiv ora vara/iarna, recuperarea dupa
repornire si respectarea termenului persistent de reincercare. Migrari la
`0011_email_retry_schedule`, fara diferente intre modele si schema PostgreSQL.

## Facturi in ciorna

Contabilitatea poate crea si consulta facturi prin POST /api/invoices,
GET /api/invoices?page=1&per_page=20 si GET /api/invoices/{id}.
Celelalte roluri, inclusiv ADMIN, nu au acces. Crearea necesita cookie JWT si
antetul X-CSRF-TOKEN, la fel ca celelalte operatii de scriere.

Exemplu de corp JSON (inlocuieste identificatorii cu furnizorul si produsul existente):

```json
{
  "supplier_id": 1,
  "series": "AB",
  "number": "001",
  "invoice_date": "2026-10-20",
  "due_date": "2026-11-20",
  "currency": "EUR",
  "items": [
    {"product_id": 1, "quantity": "3.000", "unit_price": "0.3350", "vat_rate": "19.00"}
  ]
}
```

Seria poate fi goala pentru facturi fara serie. Seria si numarul se normalizeaza
prin eliminarea spatiilor exterioare si transformare in majuscule. Accepta numai
litere ASCII, cifre si separatorii . _ / -, cu litera sau cifra la inceput.
Spatiile interne sunt respinse; zerourile initiale din numar se pastreaza.
Unicitatea furnizor + serie + numar este impusa in PostgreSQL; un duplicat produce 409.
Acestea sunt conventii interne de identificare; nu reprezinta validare fiscala.

Furnizorul si produsele trebuie sa fie active. Denumirea si unitatea produsului
sunt copiate pe linie, pentru pastrarea istoricului. O ciorna poate avea 0-100 de linii.
Scadenta nu poate preceda data facturii. Sunt acceptate monedele RON si EUR;
conversia valutara nu este inca implementata.

Cantitatea (3 zecimale), pretul (4) si TVA procentual (2, intre 0 si 100) sunt
trimise ca texte zecimale. Sumele sunt calculate de server cu Decimal:
netul liniei = cantitate * pret, rotunjit la 2 zecimale cu ROUND_HALF_UP;
TVA liniei = net rotunjit * procent / 100, rotunjit la 2 zecimale.
Totalurile antetului sunt suma valorilor liniilor. Exemplul produce net 1.01,
TVA 0.19 si total 1.20 EUR. Aceasta conventie va necesita reconciliere cu valorile
documentului furnizorului in etapa verificarii facturilor.

Starea este exclusiv DRAFT. Clientul nu poate impune totaluri, stare sau autor.
Factura, liniile si auditul sunt salvate intr-o singura tranzactie: o eroare
anuleaza intreaga operatie. Nu exista inca alocare la receptii,
verificare in trei pasi, aprobare sau plata.

Migrarea acestui pas: 0012_invoice_drafts.

Verificare dupa acest pas: 687 de teste trecute (37 noi pentru facturi), cu
PostgreSQL si Mailpit locale. Migrarea este aplicata; flask db check nu identifica
diferente intre modele si schema.

## Editarea facturilor in ciorna

PATCH /api/invoices/{id} este disponibil numai contabilitatii, cu JWT si CSRF.
Corpul contine toate campurile de la creare, plus version (versiunea citita)
si reason (motiv obligatoriu, 1-1000 de caractere dupa eliminarea spatiilor exterioare).
Lista items reprezinta toate liniile dorite dupa salvare:

- Linia existenta include id, product_id, quantity, unit_price si vat_rate.
- Linia noua contine aceleasi campuri, fara id.
- Liniile existente omise sunt eliminate din ciorna si pastrate in audit ca DELETE.
- Ordinea listei stabileste numerele liniilor, de la 1 la maximum 100.

Produsul unei linii existente este fix; pentru inlocuire, elimina linia si adauga
una noua. Liniile pastrate retin denumirea si unitatea initiale. Furnizorul si
produsele trimise trebuie sa fie active, inclusiv la editare. Antetul, cantitatile,
preturile si TVA sunt validate prin aceeasi functie ca la creare; serverul recalculeaza
toate sumele. Autorul initial si starea nu pot fi schimbate din cerere.

Serverul blocheaza randul facturii si compara version cu valoarea actuala.
O versiune veche sau o stare diferita de DRAFT produce 409; clientul reincarca
documentul inainte de a incerca din nou. O schimbare efectiva creste version cu 1.
O cerere identica dupa normalizare, cu aceleasi ID-uri si ordine, nu modifica
versiunea si nu adauga audit. Toate modificarile si auditul se salveaza atomic.
Un duplicat furnizor/serie/numar produce 409 si anuleaza intreaga editare.

Migrarea 0013_invoice_line_order permite numere pozitive temporare pentru
reordonare in tranzactie, fara conflicte cu unicitatea factura/numar linie.
Limita de 100 de linii ramane verificata de serviciu.

Verificare pentru editare: toate cele 56 de teste ale modulului facturi au trecut,
inclusiv cele 37 existente de creare si consultare si 19 noi pentru editare.
Migrarea 0013 este aplicata; flask db check nu detecteaza diferente.
Suita completa a fost rulata la pasul anterior (687 de teste); in acest pas
au fost rulate testele modulului modificat.
