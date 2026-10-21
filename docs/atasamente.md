# Documente atașate

Pachet implementat prin migrarea `0024_document_attachments`.

## Ce poți face în portal

Deschide o comandă, o recepție sau o factură și apasă **Documente**.
Echipa responsabilă poate selecta un fișier, completa **Observații fișier** și
apăsa **Încarcă fișierul**. Sunt acceptate PDF, PNG și JPG, maximum 10 MB
(10.485.760 de octeți), cel mult 50 de fișiere în istoricul unui document.
Lista include autorul, momentul încărcării, dimensiunea și observațiile.

**Descarcă** verifică accesul actual și integritatea fișierului. Fișierul este
oferit ca descărcare; nu există un URL public pentru conținut.

**Retrage** cere un motiv. Fișierul apare în continuare cu starea **Retras**,
autorul deciziei, momentul și motivul. Conținutul rămâne disponibil rolurilor
autorizate pentru consultarea istorică. Nu există ștergere sau înlocuire în loc.
Pentru o versiune nouă, retrage fișierul greșit și încarcă documentul corect.

## Permisiuni

| Document | Încarcă și retrage | Consultă și descarcă |
| --- | --- | --- |
| Comandă | Achiziții | Achiziții și Contabilitate, în limitele vizibilității comenzii |
| Recepție | Depozit | Depozit; Achiziții și Contabilitate numai după confirmarea recepției |
| Factură | Contabilitate | Contabilitate |

Depozitul nu primește lista, numele sau conținutul documentelor comerciale ale
comenzilor. Nici istoricul comenzii afișat Depozitului nu expune aceste fișiere.
Administratorul nu primește implicit drepturile echipelor. Backendul aplică
regulile și la accesul direct la URL, independent de interfață.

Comenzile și recepțiile permit adăugare/retragere în DRAFT sau CONFIRMED.
Facturile permit aceste operații numai în DRAFT, BLOCKED sau VERIFIED.
Documentele deja aprobate sau plătite oferă acces de consultare.

## Efectul asupra fluxului

- Încărcarea sau retragerea crește versiunea documentului. Operațiile începute
  pe o versiune veche primesc 409 și cer actualizarea datelor.
- Pentru o factură, ambele operații invalidează verificarea și conversia
  păstrată pe factură, închid blocajele vechi ca SUPERSEDED și readuc starea DRAFT.
  Asocierile active cu recepțiile sunt păstrate. Următoarea verificare poate
  reutiliza cursul istoric din cache.
- Fișierele nu modifică automat produsele, cantitățile, prețurile, totalurile,
  stocul sau plata. Nu există OCR. Conținutul se verifică manual față de datele
  introduse în aplicație; atașamentul este opțional în versiunea actuală.
- Încărcarea, retragerea și pregătirea descărcării au evenimente de audit.
  Evenimentele sunt vizibile în istoricul documentului, conform rolului.

## API

| Rută | Operație |
| --- | --- |
| `GET /api/documents/{kind}/{id}/attachments` | Listă paginată, inclusiv fișiere retrase |
| `POST /api/documents/{kind}/{id}/attachments` | Încărcare multipart |
| `GET /api/attachments/{id}/download` | Descărcare autentificată, cu verificarea integrității |
| `POST /api/attachments/{id}/withdraw` | Retragere cu versiune și motiv |

`kind` este exact `orders`, `receipts` sau `invoices`.
Lista acceptă `page` și `per_page`, cu maximum 100 de rezultate pe pagină.
Răspunsul include `attachments`, `total`, `document_version`, `document_status`,
`can_manage`, `max_file_bytes` și `max_attachments`. Cheia de stocare și cheia
încărcării nu sunt expuse în metadatele returnate.

Încărcarea folosește `multipart/form-data` cu exact un `file` și câmpurile text
`version`, `reason`, `upload_key`. Cheia este un UUID v4 generat de client.
Sunt necesare cookie-ul JWT și antetul `X-CSRF-TOKEN`.
Extensia, tipul declarat, semnătura fișierului, numele și dimensiunea sunt validate.
Verificarea semnăturii nu reprezintă interpretarea completă a PDF-ului sau a imaginii.

Prima încărcare întoarce 201, cu `attachment`, `document` și `replayed: false`.
Aceeași cheie, folosită de același utilizator pentru același conținut, document,
nume și motiv, întoarce documentul existent cu 200 și `replayed: true`, fără
fișier, versiune sau audit suplimentar. Refolosirea cheii cu alte date produce 409.

Retragerea primește JSON cu `version` și `reason`; răspunsul include `attachment`
și documentul actualizat în `document`.

Erorile principale sunt 400 pentru date invalide, 401 pentru sesiune/CSRF,
403 pentru rol, 404 pentru document inexistent sau invizibil, 409 pentru conflict,
413 pentru depășirea limitelor și 503 pentru indisponibilitate sau integritate
neconfirmată. Un rezultat incert la modificare cere reîncărcarea documentului
și consultarea listei înainte de o nouă operație.

## Stocare și integritate

Implicit, fișierele sunt păstrate în `backend/instance/attachments`, în afara
folderului public. `ATTACHMENT_STORAGE_PATH` poate indica alt director persistent;
o valoare goală păstrează locația implicită. Directorul trebuie să fie accesibil
procesului backend. Fișierele și configurația locală sunt excluse din Git.

`objects` conține fișierele finale, cu nume aleatorii de 64 de caractere.
Numele original nu este folosit drept cale pe disc. `staging` conține fișierele
temporare din timpul încărcării. Aplicația refuză căi și caractere de control în
numele original și verifică directoarele și fișierele pentru legături simbolice.

Un fișier este scris complet, sincronizat pe disc și publicat înainte de
confirmarea metadatelor în PostgreSQL. SHA-256 și dimensiunea se păstrează în
bază și sunt reverificate înaintea fiecărei descărcări. Conținutul lipsă sau
modificat nu este servit.

Metadatele, versiunea documentului și auditul sunt în aceeași tranzacție SQL.
Sistemul de fișiere nu face parte din tranzacția PostgreSQL. Un eșec cunoscut
înainte de commit anulează datele și elimină fișierul nou. Dacă rezultatul
commitului este incert, fișierul se păstrează pentru reconciliere, ca să nu fie
șters un document deja înregistrat. Întreruperea procesului poate lăsa fișiere
temporare sau neasociate; acestea sunt raportate, nu șterse automat.

Din `backend`, în mediul care găzduiește fișierele:

```powershell
.\.venv\Scripts\python.exe -m flask --app app check-attachments
```

Comanda verifică și fișierele retrase. Raportează documentele înregistrate,
fișierele lipsă sau corupte, fișierele neasociate și cele temporare.
Nu modifică baza, auditul sau fișierele. Un rezultat cu probleme are cod de ieșire 1.

PostgreSQL permite o singură legătură de document pentru fiecare atașament.
Un trigger interzice ștergerea, modificarea identității și conținutului metadatelor,
reactivarea sau schimbarea unei retrageri deja înregistrate.

## Repornire, backup și mutare

Fișierele sunt pe disc și sunt păstrate între repornirile backendului.
Testele verifică descărcarea dintr-o nouă instanță a aplicației cu aceeași stocare.

Pentru backup sau mutare sunt necesare **împreună** backupul PostgreSQL și
întregul director de atașamente, inclusiv fișierele retrase. Pentru o copie
consistentă, oprește scrierile aplicației pe durata capturării ambelor.
După restaurare, configurează calea și rulează `check-attachments`.
Simpla clonare a repository-ului nu mută datele sau documentele încărcate.

Backendul și frontendul web pornesc încă separat de Docker. Containerele web,
volumul de fișiere și demonstrația de backup/restaurare completă sunt următorul
pachet propus pentru livrarea portabilă.

## Verificări

- API și PostgreSQL: toate rolurile, vizibilitatea părintelui, validări, limita
  exactă de 10 MB, idempotență, retragere și protecția metadatelor.
- Atomicitate: eșec de audit, commit incert, fișier corupt, nouă instanță a aplicației
  și raportarea fișierelor neasociate fără ștergere.
- Concurență reală: aceeași cheie simultan, două încărcări pe aceeași versiune
  și încărcare în concurență cu aprobarea facturii.
- Browser cu Flask/PostgreSQL reale: document comercial cu acces pe rol,
  dovadă la recepție, factură cu fișier retras, versiune nouă, reverificare și aprobare.
  Descărcările sunt comparate prin SHA-256, inclusiv numele cu diacritice.
- UI: multipart și CSRF, extensie și dimensiune, conflict, rezultat incert,
  descărcare nereușită și expirarea sesiunii.

Testele complete folosesc un frontend separat pe 5174 și API-ul temporar pe 5201,
prin proxy HTTP real. Portalul obișnuit rămâne pe 5173. Schema PostgreSQL și
directorul de fișiere ale testului sunt temporare și sunt eliminate la final.
