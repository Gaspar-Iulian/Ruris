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
SQLAlchemy si migrarile vor gestiona tabelele si modificarile lor.

Regulile functionale sunt descrise in [procese.md](procese.md).
Aceste reguli vor ghida modelele, endpointurile si testele.
Relatiile si campurile propuse sunt descrise in [schema-date.md](schema-date.md).

## Organizarea codului

Pastram structura existenta si adaugam fisiere pe masura ce implementam functiile.

| Zona | Exemple de fisiere viitoare | Rol |
| --- | --- | --- |
| models | user.py, purchase_order.py, receipt.py, invoice.py | Date, relatii si constrangeri |
| routes | auth.py, purchases.py, warehouse.py, invoices.py | Validare cereri, acces si raspunsuri |
| services | purchases.py, receiving.py, matching.py, inventory.py | Reguli si operatii complete |
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
| Depozit | Receptii, retururi si miscari de stoc |
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
- Miscari de stoc, inclusiv iesiri si retururi.
- Cursuri valutare si jurnal de audit.
- Notificari si istoricul trimiterilor.

Sumele folosesc Decimal in Python si NUMERIC in PostgreSQL.
Parolele se pastreaza ca hash bcrypt.
JWT identifica utilizatorul; backendul verifica drepturile lui.

## Integrari ulterioare

- Cursuri BNR pentru conversia EUR in RON.
- SMTP pentru emailuri.
- Celery, Redis si un singur Celery Beat pentru sarcini periodice.

Sarcinile periodice ruleaza separat de cererile utilizatorilor.
Emailurile au istoric, reincercare la eroare si protectie impotriva duplicatelor.

## Docker

Compose va defini frontendul, backendul si PostgreSQL.
Serviciile pentru sarcinile periodice vor fi adaugate ulterior.
Datele PostgreSQL se pastreaza intr-un volum persistent.
Mutarea datelor necesita backup si restaurare, separat de codul din Git.
Secretele locale se pastreaza in .env, exclus din Git.

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
