# Portal Intern RURIS

Aplicație pentru Achiziții, Depozit și Contabilitate: **comandă → recepție → factură → verificare → aprobare → evidența plății**. Gestionează livrări parțiale, marfă necomandată, diferențe de facturare și anularea facturilor neaprobate, cu acces pe rol și audit.

## Tehnologii

| Zonă | Tehnologii |
| --- | --- |
| Backend | Python 3.14, Flask, SQLAlchemy, Flask-Migrate / Alembic, psycopg |
| Bază de date | PostgreSQL 17, constrângeri, tranzacții și blocări de rând |
| Frontend | React 19, Vite 8, CSS, Lucide React |
| Autentificare | bcrypt, Flask-JWT-Extended, cookie HttpOnly, CSRF, RBAC, Flask-Limiter |
| Integrări | Curs EUR/RON din XML BNR la data facturii, SMTP, Mailpit local |
| Rulare și teste | Docker Compose, Nginx, Gunicorn, pytest, Playwright |

## Pornire

Cu Docker Desktop / motor Linux pornit, creează `.env` din `.env.example` și completează configurația, inclusiv parola PostgreSQL și cheia JWT aleatoare de minimum 32 de octeți. Păstrează configurația existentă dacă proiectul este deja instalat.

```powershell
docker compose --profile app up -d --build --wait
docker compose --profile app exec api python -m flask --app app create-admin
```

Administratorul se creează doar la prima instalare; ulterior creează conturile echipelor din portal.
**Portal:** http://127.0.0.1:8080 · **Mailpit:** http://127.0.0.1:8025.

Servicii Compose: `web` (React/Nginx), `api` (Flask/Gunicorn), `db` (PostgreSQL), `migrate` (Alembic), `notification-worker` și `mailpit`. Baza și fișierele au volume separate; `maintenance` oferă backup/restaurare, iar `mailpit-test` izolează emailurile testelor.

## Structură și servicii backend

```text
backend/app/routes/     API, acces și validarea cererilor
backend/app/services/   reguli de business și tranzacții
backend/app/models/     tabele, relații și constrângeri
backend/migrations/     migrări Alembic
frontend/src/           interfață React
backend/tests/          teste API, PostgreSQL și concurență
frontend/tests/         teste UI și fluxuri complete
scripts/               backup, restaurare și import
docs/                  documentație detaliată
```

| Module din `backend/app/services/` | Responsabilitate |
| --- | --- |
| `auth.py`, `users.py` | Autentificare, revocare sesiuni și administrarea conturilor |
| `suppliers.py`, `products.py`, `purchase_orders.py` | Catalog, comenzi, livrare și context pentru facturare |
| `receipts.py`, `receipt_exceptions.py` | Recepții, clarificări, acceptare/respingere și intrări în stoc |
| `invoices.py`, `invoice_matching.py`, `invoice_allocations.py` | Facturi, surse eligibile și rezervarea cantităților acceptate |
| `invoice_verification.py`, `invoice_issues.py`, `invoice_payments.py`, `invoice_cancellation.py` | Verificare, blocaje, aprobare, plată și anulare |
| `exchange_rates.py`, `audit.py`, `document_history.py` | Curs BNR, audit și istoric pe document |
| `notifications.py`, `receipt_notifications.py`, `email_delivery.py`, `notification_worker.py`, `mail.py` | Sumare pe echipe, outbox, SMTP și programarea trimiterilor |
| `attachments.py`, `attachment_storage.py` | Metadate, acces, stocare și integritatea fișierelor |

Rutele apelează serviciile; serviciile aplică regulile și salvează operația împreună cu auditul. `version` detectează formularele cu date vechi; blocările PostgreSQL protejează operațiile simultane. Sumele folosesc Decimal/NUMERIC, iar previzualizarea din frontend folosește BigInt.

## Rute API principale

Toate rutele au prefixul `/api`. `{id}` reprezintă identificatorul documentului. Inventarul detaliat și accesul sunt în [permisiuni](docs/permisiuni.md).

| Metodă | Rută | Scop |
| --- | --- | --- |
| POST / GET | `/auth/login`, `/auth/logout` (POST); `/auth/me` (GET) | Sesiune |
| GET, POST, PATCH | `/users`, `/suppliers`, `/products` | Liste/creare; actualizări prin `/{id}`, `/{id}/status` sau `/{id}/role`, conform resursei |
| GET, POST, PATCH | `/purchase-orders`, `/purchase-orders/{id}` | Listare, creare, detalii și corectarea ciornei |
| POST / GET | `/purchase-orders/{id}/confirm` (POST); `/delivery`, `/invoicing`, `/history` (GET, sub același document); `/purchase-orders/overdue` (GET) | Confirmare, livrare, facturare, istoric și întârzieri |
| GET, POST, PATCH | `/receipts`, `/receipts/{id}`; POST `/receipts/unordered` | Recepții din comandă sau fără comandă |
| POST / GET | `/receipts/{id}/confirm`, `/items/{item_id}/clarify`, `/items/{item_id}/resolve` (POST, sub recepție); `/receipts/pending` (GET) | Confirmare și rezolvarea mărfii în așteptare |
| GET, POST, PATCH | `/invoices`, `/invoices/{id}` | Facturi și corectarea documentelor neaprobate |
| GET / POST | `/invoices/{id}/matching`, `/issues`, `/history` (GET); `/allocations` (GET/POST), `/allocations/release` (POST, sub factură) | Concordanță, blocaje, istoric și asocieri |
| POST / PATCH | `/invoices/{id}/verify`, `/approve`, `/pay`, `/cancel` (POST); `/declared-totals` (PATCH, sub factură) | Fluxul facturii și totalurile furnizorului |
| GET | `/stock`, `/notifications`, `/health`, `/ready` | Stoc, jurnal personal și disponibilitate |
| GET, POST | `/documents/{kind}/{id}/attachments`; GET `/attachments/{id}/download`; POST `/attachments/{id}/withdraw` | Fișiere; `kind`: `orders`, `receipts`, `invoices` |

## Roluri și reguli

**Achiziții:** catalog/comenzi și clarificări comerciale. **Depozit:** recepții și decizii fizice, fără prețuri. **Contabilitate:** facturi, asocieri, aprobare și plată. **Administrator:** conturi, fără drepturi operaționale implicite. Permisiunile sunt verificate în API.

Numai marfa acceptată intră în stoc și poate acoperi facturi; aceeași cantitate nu poate fi rezervată de două ori. Diferențele de cantitate, condiții comerciale, totaluri sau curs blochează aprobarea. Anularea înainte de aprobare eliberează asocierile și păstrează istoricul și fișierele. Emailurile sunt programate zilnic la 08:00 Europe/Bucharest, cu deduplicare și istoric personal.

## Testare și documentație

pytest verifică API-ul, regulile și concurența PostgreSQL; Playwright verifică interfața și fluxurile cu API real. Datele și emailurile testelor sunt izolate. Comenzile sunt în [acceptanță](docs/acceptanta.md), iar instalarea, backupul și restaurarea în [ghidul Docker](docs/docker.md).

[Arhitectură](docs/arhitectura.md) · [Procese](docs/procese.md) · [Schema datelor](docs/schema-date.md) · [Atașamente](docs/atasamente.md) · [Demonstrație interviu](docs/demo-interviu.md) · [Starea proiectului](docs/stare-proiect.md)

**Limite:** un depozit; stoc din intrări acceptate, fără ieșiri/retururi/ajustări; fără OCR, avansuri, plăți parțiale, transferuri bancare sau corecții după aprobare/plată. O zi fără curs BNR publicat rămâne blocată. Configurația Docker este locală; HTTPS și SMTP extern se pregătesc pentru mediul destinație.
