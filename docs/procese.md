# Procese și reguli implementate

Acest document descrie comportamentul livrat, pentru o firmă și un depozit.
Scenariile și verificările sunt în [acceptanta.md](acceptanta.md).

## Comandă și livrare

Achizițiile creează furnizori, produse și comenzi în RON sau EUR. Pozițiile
păstrează descrierea, unitatea, cantitatea, prețul, TVA și termenul. Datele
comerciale nu sunt înlocuite de modificările ulterioare ale catalogului.

Comanda se editează în ciornă și se confirmă înainte de recepție. API-ul nu
implementează modificarea, închiderea sau anularea unei comenzi confirmate.
Valorile CLOSED/CANCELLED permise în schemă nu reprezintă acțiuni livrate în portal.

Starea comercială și livrarea sunt separate: comanda rămâne „Confirmată”, iar
livrarea devine „Parțială” sau „Completă”. Restul se calculează pe fiecare poziție
din cantitatea comandată minus acceptările confirmate. Un termen trecut cu rest
pozitiv apare în întârzieri și în sumarul responsabilului din Achiziții.

## Recepție și stoc

Depozitul înregistrează recepții din comandă sau marfă fără comandă, inclusiv cu
produs încă necunoscut. Cantitatea sosită se împarte între acceptată, respinsă
și în așteptare. Numai acceptarea justificată printr-o comandă compatibilă
creează stoc și poate acoperi facturi.

Marfa necomandată și surplusul rămân în clarificări. Achizițiile identifică
produsul și comanda potrivită; Depozitul decide cantitatea acceptată sau respinsă,
cu motiv. O comandă suplimentară poate acoperi surplusul.

Acceptările ulterioare păstrează poziția fizică inițială și creează poziții
asociate acesteia. `resolved_quantity` înregistrează partea acceptată ulterior;
listele nu numără din nou aceeași marfă sosită. Se poate rezolva numai o parte
din cantitatea în așteptare.

Confirmarea, mișcarea de stoc și auditul sunt atomice. Repetarea confirmării
nu creează o a doua intrare. Stocul actual este suma intrărilor acceptate;
ieșirile, retururile, soldurile inițiale și ajustările nu sunt implementate.
Facturarea, plata și anularea facturii nu modifică acest stoc.

## Factură, asociere și aprobare

Contabilitatea pornește factura dintr-o comandă, cu condițiile precompletate.
Vede facturile existente, stările și restul de facturat. Introducerea manuală
permite poziții din mai multe comenzi ale aceluiași furnizor; legătura efectivă
se stabilește prin recepțiile asociate.

Referința furnizor + serie + număr este unică după normalizare. Mai multe facturi
pentru tranșe diferite sunt permise. Salvarea unui document distinct greșit rămâne
posibilă; aprobarea cere acoperire completă și concordanță.

O asociere rezervă o cantitate acceptată unei poziții de factură. Totalul
asocierilor ACTIVE nu poate depăși nici cantitatea acceptată, nici cantitatea
facturată. Rezervările sunt comune tuturor facturilor, inclusiv celor blocate.
Propunerea din interfață trebuie salvată; simpla afișare nu rezervă marfa.

Verificarea controlează cantitatea, furnizorul, produsul, unitatea, prețul,
moneda, TVA și totalurile documentului. Diferențele sunt păstrate ca blocaje cu
responsabil, moment și explicație. O diferență blochează întreaga factură.

Calculele folosesc Decimal: net = cantitate × preț, rotunjit la doi zecimali;
TVA se calculează din net și se rotunjește pe poziție; totalurile însumează
pozițiile. Frontendul folosește BigInt pentru previzualizare. Netul, TVA și totalul
furnizorului se introduc separat și sunt obligatorii la verificare. O diferență
de un ban blochează; previzualizarea nu substituie documentul furnizorului.

Fluxul este DRAFT → BLOCKED sau VERIFIED → APPROVED → PAID. Reverificarea poate
rezolva blocajele după corectare sau sosirea mărfii. Aprobarea repetă verificarea
pe datele curente. Plata este o evidență integrală cu referință și moment,
fără transfer bancar. Nu există avansuri sau plăți parțiale.

## Anularea unei înregistrări greșite

Numai Contabilitatea poate anula DRAFT, BLOCKED sau VERIFIED, cu motiv și
versiunea curentă. Operația eliberează asocierile, închide blocajele curente,
elimină verificarea valutară și înregistrează autorul și momentul în aceeași
tranzacție. Nu modifică stocul sau istoricul emailurilor.

Factura CANCELLED rămâne vizibilă, cu poziții, fișiere și audit; nu mai consumă
cantitatea înregistrată pe comandă și nu poate fi editată sau reverificată.
Unicitatea referinței se păstrează și după anulare. Fișierele existente pot fi
descărcate, dar nu se mai încarcă sau retrag fișiere.

APPROVED și PAID nu pot fi anulate prin acest flux. Documentele de corecție
pentru aceste situații necesită un modul separat.

## Curs valutar

RON folosește curs 1. Pentru EUR, aplicația preia XML-ul anual public BNR și
caută data exactă a facturii. Reține sursa, checksumul, data, cursul și conversia
în RON. Cache-ul este protejat împotriva modificării și ștergerii.

O dată fără curs publicat și o preluare eșuată produc blocaje distincte. Nu se
folosește automat cursul zilei precedente sau cel curent. Un curs local valid
pentru data respectivă permite verificarea fără o nouă preluare. Cursul reținut
pentru o factură aprobată nu se schimbă automat.

## Acces, audit și concurență

Rolurile sunt ADMIN, ACHIZITII, DEPOZIT și CONTABILITATE. Administratorul gestionează
conturile, fără drepturi operaționale implicite. Depozitul primește o proiecție
fără prețuri și date de plată. Verificarea drepturilor se face în API, inclusiv
pentru istoric și fișiere. Contul și rolul curent sunt verificate la fiecare cerere.

Auditul păstrează autorul uman sau procesul, operația, documentul, momentul,
motivul și valorile relevante înainte/după. Nu include parole sau tokenuri.
Este salvat în tranzacția operației și protejat în PostgreSQL la UPDATE/DELETE.

`version` respinge salvarea dintr-un formular vechi. Blocările de rând PostgreSQL
protejează cantitățile și tranzițiile simultane. Aprobarea și anularea aceleiași
facturi nu pot reuși amândouă. După un rezultat incert, portalul cere reîncărcarea
datelor înainte de o nouă operație.

## Emailuri și clarificări

Workerul verifică periodic programul și generează sumarul zilnic la 08:00,
Europe/Bucharest. Sunt implementate întârzierile pentru responsabilul din
Achiziții, recepțiile care cer clarificare comercială, marfa în așteptarea
deciziei Depozitului și facturile blocate pentru Contabilitate. Nu există sumar
separat pentru facturi scadente.

Outboxul păstrează mesajul, destinatarul, încercările și rezultatul. Cheia
utilizator + tip + transport + zi previne programarea repetată. Un mesaj deja
trimis nu este trimis din nou pentru modificări apărute în aceeași zi.
Înainte de trimitere se verifică din nou destinatarul și conținutul curent.

Eșecurile cunoscute pot fi reîncercate, cel mult de trei ori. O acceptare SMTP
incertă devine UNKNOWN și nu se retrimite automat: SMTP nu garantează livrare
exact o dată. SENT înseamnă acceptat de serverul SMTP, nu confirmat citit.

„Clarificări” arată problemele curente. „Notificări” este istoricul personal al
destinatarului, filtrat și după rolul său actual; nu este inbox comun de echipă.
Rezolvarea problemei o elimină din sumarele viitoare, fără ștergerea mesajelor trimise.

## Ordinea documentelor în portal

Sortarea se aplică în PostgreSQL înainte de paginare, cu identificatorul ca
departajare stabilă. Permisiunile și câmpurile vizibile rămân specifice rolului.

| Listă | Ordine implicită |
| --- | --- |
| Facturi | Blocate → ciorne → verificate → aprobate → plătite → anulate; scadența cea mai apropiată în fiecare categorie |
| Recepții | Confirmate cu marfă în așteptare → ciorne, vizibile numai Depozitului → confirmate rezolvate → anulate; data sosirii în fiecare categorie |
| Comenzi | Confirmate întârziate → ciorne, vizibile numai Achizițiilor → livrate parțial → nerecepționate → livrate complet → închise → anulate; cel mai apropiat termen restant în fiecare categorie |
| Catalog și conturi | Înregistrări active înaintea celor inactive |

Întârzierile păstrează ordinea după cel mai vechi termen. Istoricul și jurnalul
notificărilor rămân cronologice, cu cele mai recente operații primele.

Istoricul recepției din portal grupează antetul și pozițiile din aceeași operație;
motivul apare o singură dată, iar pozițiile se pot extinde. Paginarea numără
operații întregi. Auditul detaliat este păstrat integral; API-ul fără `grouped=1`
continuă să ofere evenimentele individuale. Gruparea folosește momentul complet,
autorul și motivul, fără trunchierea timestampului la secunda afișată.
