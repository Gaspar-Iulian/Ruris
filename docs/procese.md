# Procese si reguli

Acesta este proiectul functional pentru prima versiune.
Regulile de mai jos sunt propuneri de implementare, nu functii deja existente.

## Limitele primei versiuni

- O firma si un depozit.
- Cont individual pentru fiecare persoana, cu un rol principal.
- Introducere manuala a documentelor si atasarea fisierelor justificative.
- Comenzi si facturi in RON sau EUR.
- Aprobarea si evidenta platii; fara initierea transferurilor bancare.
- Fara OCR, integrare bancara sau integrare cu un program contabil in prima versiune.

## Problemele si raspunsul aplicatiei

| Problema | Comportament propus |
| --- | --- |
| Informatii separate intre echipe | Comanda, receptiile si factura sunt legate in aceeasi baza |
| Livrare partiala | Mai multe receptii pe comanda, cu rest de livrat calculat pe pozitie |
| Marfa necomandata sau in plus | Exceptie vizibila, cu responsabil si actiune de clarificare |
| Factura pentru marfa nelivrata | Blocare cu motiv si cantitatea lipsa |
| Aceeasi marfa facturata de doua ori | Alocari cantitative la receptii si control cumulativ |
| Stoc necunoscut | Evidenta tuturor intrarilor, iesirilor, retururilor si ajustarilor |
| Intarzieri observate prea tarziu | Termene pe pozitii si sumar periodic catre achizitii |
| Modificari greu de urmarit | Audit in aceeasi tranzactie cu operatia |

## Comenzi

O comanda are furnizor, moneda, responsabil si pozitii.
Fiecare pozitie pastreaza produsul, unitatea de masura, cantitatea,
pretul agreat si termenul de livrare.
Pretul si descrierea de pe document raman pastrate chiar daca se modifica catalogul.

Comanda se poate edita liber in ciorna. Confirmarea fixeaza conditiile pentru receptie si verificarea facturii.
O modificare ulterioara necesita motiv, audit si reverificarea documentelor afectate.
Nu reducem cantitatea comandata sub cantitatea deja acceptata fara o corectie explicita.
Restul nelivrat poate fi inchis explicit, cu motiv; nu dispare automat din evidenta.

O pozitie este intarziata daca termenul a trecut si exista rest deschis de livrat.
Starea de livrare se calculeaza din cantitati: nereceptionata, partiala sau completa.
Anularea si inchiderea sunt actiuni separate de starea livrarii.

## Receptii

O receptie are data, furnizor, document de livrare, autor si pozitii.
Fiecare pozitie se poate lega la o pozitie de comanda.
Legatura este optionala la inregistrare, pentru a putea raporta marfa necomandata.
Furnizorul, produsul si unitatea de masura trebuie sa corespunda la asociere.

Se separa cantitatea sosita fizic de cantitatea acceptata, respinsa sau in asteptarea clarificarii.
Doar cantitatea acceptata printr-o receptie confirmata intra in stocul disponibil
si poate justifica o factura.
Surplusul si produsele necomandate raman vizibile in asteptare pana la o decizie.
Achizitiile pot justifica acceptarea printr-o comanda sau modificare explicita,
fara a rescrie faptul ca marfa a sosit initial fara acoperire.

Confirmarea receptiei, miscarea de stoc si auditul se salveaza impreuna.
O receptie confirmata se corecteaza prin operatii urmarite, nu prin stergere.

## Stoc

Stoc disponibil = sold initial + intrari acceptate - iesiri - retururi + ajustari semnate.
Marfa in asteptare se afiseaza separat de stocul disponibil.
Orice ajustare necesita motiv si persoana responsabila.
Nu permitem stoc disponibil negativ in prima versiune.
Plata sau facturarea nu modifica stocul fizic.
O iesire obisnuita de marfa nu anuleaza faptul ca marfa a fost receptionata pentru facturare.

## Facturi si verificare

Factura pastreaza furnizorul, seria, numarul, data, scadenta, moneda,
pozitiile, TVA, totalurile si documentul atasat.
Seria si numarul normalizate sunt unice pentru acelasi furnizor.
Pozitiile pot acoperi mai multe comenzi si receptii ale aceluiasi furnizor.
Legaturile se fac pe pozitii, nu doar printr-un numar de comanda pe factura.

O alocare leaga o pozitie de factura de o cantitate acceptata dintr-o receptie.
Suma alocarilor active nu poate depasi cantitatea eligibila a receptiei.
Alocarile retinute pentru facturile in verificare impiedica utilizarea aceleiasi cantitati de doua ori.
Anularea sau corectarea unei facturi elibereaza alocarile conform operatiei explicite.
Factura platita se corecteaza printr-un flux documentat, pastrand istoricul platii.

Verificarea compara furnizorul, produsul, unitatea de masura, cantitatile,
preturile agreate, moneda, TVA si totalurile.
Prima versiune foloseste concordanta cantitativa si de pret fara tolerante comerciale.
Rotunjirea monetara se aplica dupa o regula documentata si uniforma.
O diferenta de moneda fata de comanda necesita clarificare explicita;
conversia pentru raportare in RON nu transforma automat preturile in preturi concordante.

Propunere pentru prima versiune: o diferenta blocheaza intreaga factura.
Plata partiala si avansurile necesita reguli suplimentare si raman in afara primei versiuni.
O factura conforma devine eligibila; contabilitatea aproba explicit plata.
Inaintea aprobarii se repeta verificarea pe datele curente.
Aplicatia nu ofera o actiune generala de ignorare a diferentelor.

Un retur sau o corectie care afecteaza alocari invalideaza verificarea si aprobarea neplatita.
Pentru facturile deja platite se deschide o exceptie de rezolvat, fara stergerea istoricului.
Fiecare blocaj indica motivul, documentele implicate, responsabilul si data aparitiei.
Motivele de blocare sunt separate de starea documentului, deoarece pot exista simultan.

## Curs valutar

Se pastreaza suma originala, cursul, sursa, data cursului si suma in RON.
RON foloseste curs 1. EUR foloseste cursul BNR pentru data facturii.
Propunere pentru o zi fara publicare: ultimul curs publicat anterior, cu data afisata explicit.
Aceasta politica trebuie confirmata cu contabilitatea inainte de utilizarea reala.
Daca un curs necesar nu a fost publicat sau nu poate fi preluat, factura asteapta cursul.
La indisponibilitatea sursei se foloseste doar un curs local corespunzator regulii stabilite.
Nu se substituie cursul din ziua curenta pentru o factura istorica.
Cursul unei facturi aprobate nu se actualizeaza automat.
Sumele se calculeaza cu Decimal si se stocheaza ca NUMERIC.

## Acces si audit

Achizitiile modifica comenzile; depozitul confirma receptiile si miscarile de stoc;
contabilitatea gestioneaza facturile si aprobarea platii.
Fiecare echipa vede din documentele celorlalte doar informatiile necesare fluxului.
Depozitul nu are nevoie de preturi sau date de plata pentru a receptiona marfa.
Administratorul tehnic gestioneaza conturile; acest rol nu acorda automat drept de aprobare a platii.
Accesul se verifica pentru operatii, documente, liste, exporturi si atasamente.
Conturile dezactivate si modificarile de rol trebuie sa aiba efect chiar daca exista un JWT neexpirat.

Auditul pastreaza autorul, actiunea, documentul, momentul, motivul si valorile relevante schimbate.
Nu se inregistreaza parole, tokenuri sau alte secrete.
Actiunile automate identifica procesul care le-a executat.
Jurnalul nu poate fi editat sau sters din aplicatie.
Momentele se stocheaza in UTC si se afiseaza in Europe/Bucharest.

## Operatii simultane

Confirmarea receptiei, aprobarea facturii si miscarea stocului folosesc tranzactii PostgreSQL.
Verificarile se repeta in tranzactie, cu blocarea randurilor relevante cand este necesar.
Constrangerile bazei impun unicitatea documentelor si validitatea cantitatilor individuale.
Limitele cumulative intre documente se verifica prin servicii si blocari, nu doar in React.
Operatiile de confirmare suporta reluarea cererii fara dublarea efectului.
Formularele detecteaza o versiune depasita a documentului inainte de salvare.

## Emailuri periodice

Un sumar zilnic la 08:00 Europe/Bucharest include doar problemele inca active.
Achizitiile primesc intarzierile si diferentele care necesita discutia cu furnizorul.
Depozitul primeste receptiile de clarificat; contabilitatea primeste blocajele si scadentele.
Continutul respecta aceleasi permisiuni ca interfata.
Rezolvarea problemei o elimina din urmatoarele sumare.

Notificarile se inregistreaza in baza, apoi un worker incearca trimiterea prin SMTP.
Se pastreaza destinatarul, perioada sumarului, incercarile si rezultatul.
O cheie unica pe destinatar si perioada previne programarea repetata a aceluiasi sumar.
Erorile se reincearca; o intrerupere dupa acceptarea de catre SMTP poate totusi produce o retrimitere.
Nu promitem livrare exact o data prin SMTP.

## Scenarii de acceptare

| Scenariu | Rezultat asteptat |
| --- | --- |
| Comandat 100, acceptat 60, facturat 100 | Factura blocata: lipsesc 40 receptionate |
| Comandat 100, acceptat 60, facturat 60 | Eligibila daca preturile si celelalte verificari corespund |
| Ulterior acceptat inca 40 | Comanda completa; factura blocata poate fi reverificata |
| Doua facturi pentru aceleasi 60 acceptate | Alocarile cumulative nu depasesc 60, inclusiv la cereri simultane |
| Doua apasari pe confirmarea aceleiasi receptii | O singura intrare in stoc |
| Produs necomandat sau surplus | Inregistrat in asteptare, fara cresterea stocului disponibil |
| Retur pentru marfa alocata unei facturi aprobate neplatite | Aprobarea se invalideaza si se cere rezolvare |
| Termen depasit si rest deschis | Comanda apare in sumarul achizitiilor |
| Depozitul apeleaza direct API-ul de aprobare factura | Acces refuzat |
| Curs istoric indisponibil | Factura asteapta cursul, fara conversie la cursul curent |

## Decizii de validat cu firma

- Blocarea intregii facturi sau permiterea aprobarii unei parti.
- Politica pentru zilele fara curs publicat si regula de rotunjire monetara.
- Destinatarii, frecventa sumarului si responsabilitatea pentru fiecare tip de exceptie.
- Necesitatea avansurilor, tolerantei de pret si documentelor de corectie in prima versiune.

Aceste decizii nu impiedica pregatirea modelelor de baza.
Nu activam comportamente dependente de o politica neconfirmata in utilizarea reala.
