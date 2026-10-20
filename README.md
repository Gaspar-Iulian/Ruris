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
PostgreSQL a fost pornit prin Compose, iar ambele migrari au fost aplicate si verificate.
Nu exista inca endpointuri pentru conturi sau autentificare.
Flask-Migrate este configurat, iar folderul `backend/migrations` este initializat.

## Pornire backend pe Windows

La prima utilizare, creeaza `.env` din `.env.example` in radacina proiectului
si seteaza o parola proprie, conform sectiunii PostgreSQL de mai jos.

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
Rolurile permise sunt ADMIN, PURCHASING, WAREHOUSE si ACCOUNTING.
Nu exista rol implicit: acesta trebuie ales explicit.

`set_password()` foloseste bcrypt cu salt aleator si factor 12.
Parola trebuie sa aiba minimum 12 caractere si maximum 72 de octeti UTF-8.
Limita in octeti poate fi atinsa mai repede de caracterele cu diacritice.
Parolele prea lungi sunt respinse, fara trunchiere.
`check_password()` verifica parola fata de hash.
Schimbarea parolei creste `token_version`, pregatind invalidarea sesiunilor viitoare.
Verificarea JWT si operatiile de administrare a conturilor vor fi implementate separat.

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
CREATE, UPDATE, PASSWORD_CHANGE, ACTIVATE si DEACTIVATE.
Nu exista inca endpointuri care modifica utilizatori, deci nici operatii de cont auditate automat.

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

Separat, `tests/test_postgres.py` verifica comportamentul pe PostgreSQL real.
Aceste teste sunt omise implicit. Pentru rularea tuturor testelor, dupa pornirea bazei
si aplicarea migrarilor, din folderul `backend`, in PowerShell:

```powershell
$env:RUN_POSTGRES_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
Remove-Item Env:RUN_POSTGRES_TESTS
```

Se foloseste baza configurata in `.env`. Testele ruleaza in tranzactii exterioare
anulate la final; commiturile din teste sunt izolate prin savepointuri.
Nu stergem tabele, nu dezactivam triggerul si nu golim volumul.
Secventele de identificatori pot avansa chiar daca datele testului sunt anulate.

Verificarile includ salvarea si recitirea utilizatorilor si auditului, unicitatea emailului,
rolurile permise, autorul obligatoriu, blocarea UPDATE/DELETE asupra auditului
si anularea modificarii contului daca auditul sau operatia esueaza.

Ultima verificare: 53 de teste trecute, migrari la `0002_audit_events`,
fara diferente intre modele si schema PostgreSQL.
