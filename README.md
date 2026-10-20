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

Nu exista inca evidenta stocului. Stocul va fi calculat din miscarile de marfa,
inclusiv o miscare explicita pentru soldul initial.

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
