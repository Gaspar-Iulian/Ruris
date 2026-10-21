# Arhitectura

## Componente

```text
Browser (React)
      |
      | API REST / JSON
      v
Backend (Flask)
      |
      | SQLAlchemy
      v
PostgreSQL
```

React afiseaza paginile si trimite cereri catre Flask.
Flask verifica utilizatorul, permisiunile si regulile aplicatiei.
Doar backendul acceseaza baza de date.

Backendul este o singura aplicatie, organizata pe module.
SQLAlchemy și migrările Alembic gestionează tabelele și modificările lor.

Regulile functionale sunt descrise in [procese.md](procese.md).
Relațiile implementate sunt descrise în [schema-date.md](schema-date.md).
Accesul implementat este descris în [permisiuni.md](permisiuni.md).

## Organizarea codului

Pastram structura existenta si adaugam fisiere pe masura ce implementam functiile.

| Zona | Exemple de module | Rol |
| --- | --- | --- |
| models | user.py, purchase_order.py, receipt.py, invoice.py | Date, relatii si constrangeri |
| routes | auth.py, purchase_orders.py, receipts.py, invoices.py | Validare cereri, acces si raspunsuri |
| services | purchase_orders.py, receipts.py, invoice_allocations.py, invoice_cancellation.py | Reguli si operatii complete |
| services | exchange_rates.py, notifications.py, audit.py | Integrari si trasabilitate |
| tests | teste pentru fiecare flux | Verificarea comportamentului si accesului |

Rutele apeleaza serviciile. Serviciile folosesc modelele si gestioneaza tranzactiile.
Regulile de facturare si stoc au un singur loc de implementare in backend.
React afiseaza rezultatul verificarilor si motivele blocarii.
Nu cream servicii separate pentru fiecare echipa: toate folosesc aceleasi documente.

## Roluri

Fiecare persoana are un cont propriu si un rol.

| Rol | Responsabilitati |
| --- | --- |
| Achizitii | Furnizori, comenzi si urmarirea livrarilor |
| Depozit | Recepții și acceptarea/respingerea mărfii |
| Contabilitate | Facturi, verificari si aprobarea platii |
| Administrator | Utilizatori si configurari |

Permisiunile se verifica in backend pentru fiecare operatie.
Ascunderea unui buton in React nu este o masura suficienta de acces.

## Flux principal

1. Achizitiile creeaza comanda si pozitiile ei.
2. Depozitul inregistreaza una sau mai multe receptii.
3. Contabilitatea inregistreaza factura si pozitiile ei.
4. Backendul compara factura cu comanda si receptiile acceptate.
5. Diferentele blocheaza aprobarea si afiseaza motivul.
6. Contabilitatea aproba facturile eligibile pentru plata.

O receptie partiala lasa comanda deschisa pentru cantitatea ramasa.
Marfa necomandata necesita clarificare inainte de acceptare.
Aceeasi cantitate receptionata nu poate justifica mai multe facturi.
Modificarile relevante pastreaza utilizatorul, data si valorile schimbate.

## Date principale

- Utilizatori si roluri.
- Furnizori si produse.
- Comenzi si pozitii de comanda.
- Receptii si pozitii de receptie.
- Facturi, pozitii si alocari la receptii.
- Mișcări de intrare în stoc; ieșirile și retururile sunt extinderi viitoare.
- Cursuri valutare si jurnal de audit.
- Notificari si istoricul trimiterilor.

Sumele folosesc Decimal in Python si NUMERIC in PostgreSQL.
Parolele se pastreaza ca hash bcrypt.
JWT identifica utilizatorul; backendul verifica drepturile lui.

## Integrări și sarcini periodice

- Cursuri BNR implementate pentru conversia EUR în RON, la data exactă a facturii.
- SMTP extern pentru emailuri; transportul local de test prin Mailpit este implementat.
- Celery, Redis si Celery Beat raman o optiune pentru extinderea executiei sarcinilor.

Pentru etapa locala este implementat workerul CLI `run-notification-worker`,
separat de procesul HTTP. Verifica ora Europe/Bucharest, ruleaza sumarul zilnic
si respecta next_attempt_at din PostgreSQL pentru reincercari. Nu porneste automat
din create_app() și nu necesită dependențe suplimentare. Profilul Docker `app`
îl rulează într-un container separat, cu repornire automată.

Sarcinile periodice ruleaza separat de cererile utilizatorilor.
Emailurile au istoric, reincercare la eroare si protectie impotriva duplicatelor.

## Docker

Profilul `app` definește frontendul React compilat servit de Nginx, API-ul Flask
prin Gunicorn, PostgreSQL, migrarea și procesul de notificări. Browserul folosește
o singură adresă; Nginx trimite `/api/` către API-ul intern. Ordinea de pornire
folosește verificări de disponibilitate și finalizarea cu succes a migrării.

Baza și documentele sunt păstrate în volume distincte. Backupul oprește temporar
serviciile care scriu, salvează baza și fișierele și le repornește. Restaurarea
verifică integritatea și refuză suprascrierea unei destinații cu date existente.
Secretele locale rămân în `.env`, în afara imaginilor și a repository-ului.

Comenzile de instalare și mutare sunt în [ghidul Docker](docker.md).

## Ordinea implementarii

1. PostgreSQL prin Docker Compose.
2. Flask si un endpoint de verificare a functionarii.
3. Conectarea bazei de date si migrarile.
4. Utilizatori, autentificare si permisiuni.
5. Comenzi, receptii si miscari de stoc.
6. Facturi si verificarea diferentelor.
7. Cursuri valutare si notificari.
8. Interfata React, construita treptat pentru fluxurile disponibile.
9. Pornirea intregii aplicatii prin Compose si documentarea livrarii.

Testele pentru reguli, permisiuni si audit se adauga odata cu fiecare functie.

Fluxurile se construiesc pe rand, cu paginile React necesare fiecaruia.
Auditul se adauga de la primele operatii care modifica date.
Portabilitatea se verifica la final prin pornire dintr-o clona noua a proiectului.
