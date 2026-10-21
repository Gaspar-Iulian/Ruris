# Demonstrație pentru interviu

Scenariu de aproximativ 20 de minute. Folosește date demonstrative cu referințe
noi, fără anularea sau schimbarea documentelor reale deja introduse.

## Pregătire

1. Pornește Docker Desktop și `docker compose --profile app up -d --build --wait`.
2. Deschide portalul la http://127.0.0.1:8080 și Mailpit la http://127.0.0.1:8025.
3. Pregătește câte un cont activ pentru Achiziții, Depozit și Contabilitate, din
   contul administratorului. Nu pune parolele în README sau în prezentare.
4. Păstrează separat conturile, documentele și inboxul testelor automate.
5. Creează un backup conform [docker.md](docker.md).

## Problema, în 30 de secunde

„Achizițiile știu ce s-a comandat, Depozitul ce a sosit, iar Contabilitatea ce
cere furnizorul la plată. Portalul leagă aceste informații și permite aprobarea
numai pentru marfă acceptată și condiții comerciale conforme. Fiecare operație
are autor, moment și istoric.”

## 1. Comandă și livrare în tranșe — 5 minute

Intră ca Achiziții. Creează un furnizor și un produs cu SKU nou. Creează o
comandă de 100 BUC, preț 2 RON, TVA 0 pentru un exemplu aritmetic simplu, cu
termen în trecut pentru a apărea în întârzieri. Confirmă comanda.

Intră ca Depozit. Creează o recepție de 77 și confirmă toate cele 77 ca acceptate.
Arată stocul 77 și restul 23. Depozitul vede cantități, fără prețurile comerciale.

Contabilitatea creează din comandă factura pentru 100: net 200, TVA 0, total 200.
Propune și salvează asocierea disponibilă, apoi verifică. Lipsesc 23 acceptate;
factura rămâne blocată și nu există acțiune de plată disponibilă.

Depozitul înregistrează și confirmă a doua recepție de 23. Stocul devine 100,
livrarea „Completă”, iar comanda rămâne comercial „Confirmată”. Contabilitatea
asociază diferența și verifică din nou: factura devine „Verificată”.

## 2. Totaluri, document și plată — 3 minute

Arată netul, TVA și totalul calculate, separat de valorile declarate pe document.
O sumă declarată diferită cu un ban produce blocaj; corectează cu motiv și verifică.
Atașează un PDF demonstrativ. Încărcarea schimbă versiunea și cere reverificare.

Aprobă explicit, apoi înregistrează plata cu referință. Aplicația ține evidența
plății; nu execută transferuri bancare. Deschide istoricul și arată autorul,
operația, momentul, motivul și modificările.

Pentru un exemplu separat de TVA: 5 × 15 RON, TVA 19% de pe documentul
demonstrativ, rezultă net 75, TVA 14,25 și total 89,25. Cota este un exemplu de
calcul, nu o valoare impusă automat pentru toate produsele.

## 3. Duplicat și anulare — 3 minute

Folosește o comandă nouă cu 5 BUC deja acceptate. Salvează o factură și asociază
cele 5. Salvează o a doua factură cu referință diferită pentru aceeași marfă:
nu poate folosi cantitățile deja rezervate de prima.

Pe prima factură, înainte de aprobare, apasă „Anulează factura”, scrie un motiv
și confirmă. Arată starea „Anulată”, motivul și auditul. Asocierile se eliberează;
PDF-ul rămâne descărcabil, stocul rămâne 5. Factura corectă poate acum folosi marfa.
Factura anulată rămâne în evidență și aceeași referință nu poate fi reutilizată.

Anularea nu este disponibilă pentru facturi aprobate sau plătite. Documentele
de corecție pentru aceste stări reprezintă o extindere distinctă.

## 4. Marfă necomandată — 3 minute

Depozitul înregistrează 10 unități fără comandă și le lasă în așteptare.
Stocul nu crește. Achizițiile identifică produsul și creează/asociază o comandă
pentru partea justificată. Depozitul acceptă 6 și respinge 4, cu motive.
Stocul crește doar cu 6; istoricul arată sosirea inițială și deciziile ulterioare.

Aceeași regulă se aplică surplusului: pentru restul în plus se poate crea o
comandă suplimentară, fără rescrierea recepției inițiale.

## 5. EUR și notificări — 3 minute

Pentru o factură EUR folosește o zi cu curs BNR publicat și condiții identice
cu ale comenzii EUR. Arată data exactă, cursul, sursa și totalul în RON.
Un weekend fără curs publicat produce blocaj explicit; aplicația nu alege
singură altă dată. Dacă sursa este indisponibilă și nu există cache pentru acea
dată, prezintă blocajul, fără introducerea unui curs inventat.

Arată „Clarificări” ca situații curente și „Notificări” ca istoric al emailurilor
personale. Workerul generează sumarul la 08:00 Europe/Bucharest. În instalarea
demonstrativă LOCAL_MAILPIT, o execuție manuală se poate porni cu:

```powershell
docker compose --profile app exec api python -m flask --app app send-notification-emails
```

Un sumar trimis deja în aceeași zi nu este retrimis automat pentru același
destinatar și tip. Pentru prima trimitere demonstrativă, pregătește un destinatar
nou fără sumar trimis în ziua respectivă. SENT înseamnă acceptat de serverul SMTP;
Mailpit arată mesajul local, nu livrarea la un furnizor extern.

## Explicații tehnice de reținut

| Concept | Explicație pentru interviu |
| --- | --- |
| bcrypt | Baza păstrează hashul parolei, nu parola în clar |
| JWT și revocare | Cookie HttpOnly, CSRF la modificări, cont/rol curent și token_version verificate în backend; logout revocă identificatorul sesiunii |
| RBAC | Rolul limitează operațiile și informațiile; ascunderea butonului nu înlocuiește verificarea API |
| Tranzacție | Operația, stocul/asocierile și auditul se confirmă sau se anulează împreună |
| Blocare și versiune | Blocarea protejează operațiile simultane; versiunea detectează formularul cu date vechi |
| Decimal și NUMERIC | Calcule exacte la precizia definită; BigInt reproduce previzualizarea fără erori de virgulă mobilă |
| Asociere cantitativă | Aceeași marfă nu poate acoperi simultan două facturi peste cantitatea acceptată |
| Outbox | Mesajul și încercările rămân în bază; rezultatele SMTP incerte nu sunt retrimise automat |
| Fișiere | Conținut în volum, metadate și SHA-256 în bază; descărcare autentificată și backup împreună |
| Docker | Aceleași servicii pe alt PC; clonarea codului nu mută baza și fișierele, pentru acestea folosim backup/restaurare |

## Dovezi și limite

Arată [matricea de acceptanță](acceptanta.md) și rezultatele datate din
[starea proiectului](stare-proiect.md). Testele includ PostgreSQL concurent,
browser cu API real și restaurarea fișierelor, nu numai API simulat.

Prezintă limitele: stoc de intrări acceptate fără ieșiri/retururi, fără OCR,
plăți parțiale sau integrare bancară. Instalarea livrată este locală; HTTPS,
SMTP extern și operarea pe infrastructura firmei se pregătesc în funcție de mediu.
