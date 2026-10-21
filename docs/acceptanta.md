# Acceptanță și verificare

Documentul descrie ce se livrează pentru cerințele aplicației și cum se verifică.
Rezultatele execuției sunt consemnate în [starea proiectului](stare-proiect.md).

## Matrice cerință–implementare–test

| Cerință / situație | Implementare | Dovezi automate |
| --- | --- | --- |
| Conturi și acces separat | bcrypt, JWT în cookie HttpOnly, CSRF, rol verificat în API, stare activă și versiune sesiune | `test_login`, `test_logout`, `test_permissions`, `test_user_role`, `test_user_status`, `test_jwt_config` |
| Cine, ce, când | Audit în tranzacția operației, cu snapshoturi, autor și motiv; trigger împotriva modificării și ștergerii | `test_audit`, `test_postgres`, `test_document_history` |
| Comenzi și termene | Furnizor, produse, cantități, prețuri, TVA, monedă și termen pe poziție | `test_purchase_orders`, `test_order_delivery_summary` |
| Recepție parțială / mai multe tranșe | Cantități sosite, acceptate, respinse și în așteptare; rest de livrat calculat din acceptări | `test_receipts`; flux browser 100 → 77 + 23 |
| Marfă necomandată / surplus / produs necunoscut | Recepție în așteptare, asociere comercială de către Achiziții, decizie fizică de către Depozit | `test_receipt_exceptions`, `test_receipt_exception_concurrency`; fluxuri browser pentru marfă necunoscută și surplus |
| Stoc din marfa acceptată | Mișcare de intrare atomică cu confirmarea; cantitățile în așteptare și cele respinse sunt excluse | `test_receipts`, `test_receipt_exceptions`; verificări de sold în browser |
| Facturi greșite sau fără marfă | Asociere cantitativă comandă–recepție–factură și blocaje persistate | `test_invoice_allocations`, `test_invoice_verification`; flux browser 100 facturat / 77 acceptat |
| Dublă folosire a aceleiași mărfi | Limită cumulativă pe recepție, inclusiv între facturi, sub blocare PostgreSQL | `test_invoice_allocations`, `test_invoice_allocation_concurrency`; flux browser cu două facturi |
| Calculul totalului | Cantitate × preț; TVA calculat și rotunjit pe fiecare poziție; sumarea pozițiilor | `test_invoices`, `test_invoice_declared_totals`, `amounts.spec.js` |
| Compararea cu factura furnizorului | Net, TVA și total declarate separat; diferența de un ban blochează | `test_invoice_declared_totals`; flux browser cu total greșit și corectare |
| EUR / curs automat | XML public BNR pe anul facturii, data exactă, cache imuabil și conversie reținută la aprobare | `test_exchange_rates`; fluxuri browser EUR cu XML controlat în serverul de test |
| Aprobarea și evidența plății | Repetarea verificării la aprobare; plata numai după aprobare, cu referință și moment | `test_invoice_approval`, `test_invoice_payments`; flux browser până la PAID |
| Anularea unei înregistrări greșite | CANCELLED numai înainte de aprobare, cu motiv; eliberarea asocierilor și închiderea blocajelor, fără modificarea stocului | `test_invoice_cancellation`; flux browser cu duplicat, PDF reținut și factură corectă |
| Emailuri periodice pe echipe | Worker zilnic, outbox, deduplicare, reîncercări și istoric per destinatar | `test_notifications`, `test_receipt_notifications`, `test_blocked_invoice_notifications`, `test_notification_worker`, `test_email_concurrency` |
| Documente justificative | PDF/PNG/JPG, descărcare autentificată, checksum, retragere cu motiv și păstrare istorică | `test_attachments`, `test_attachment_concurrency`; fluxuri browser și descărcări comparate prin SHA-256 |
| Mutare pe alt PC | Imagini Docker, volume, migrări, backup al schemei public și documentelor; restaurare în destinație goală | `test_deployment`; fluxuri browser prin Nginx/Gunicorn și `docker-restore.spec.js` |

Numele din coloana testelor sunt fișiere din `backend/tests` sau `frontend/tests`.
Un test cu sursa BNR simulată verifică regula și tratarea erorilor, nu disponibilitatea
continuă a BNR. SMTP real extern necesită configurarea furnizorului; integrarea
SMTP locală este verificată cu Mailpit separat.

## Rularea verificărilor backend

Din rădăcina repository-ului, cu `.env` configurat și Docker pornit:

```powershell
docker compose --profile tests up -d db mailpit-test
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:RUN_POSTGRES_TESTS = '1'
$env:RUN_MAILPIT_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Crearea mediului și instalarea dependențelor se fac numai când nu sunt deja
pregătite. Testele creează scheme temporare și le elimină; nu creează facturi
demonstrative în schema public a utilizatorului. Testele concurente folosesc
conexiuni distincte, nu doar două apeluri succesive în aceeași sesiune.

## Interfață și fluxuri reale

Cu Node compatibil cu `frontend/package.json` instalat:

```powershell
cd frontend
npm.cmd ci
npm.cmd test -- --grep-invert 'real Flask and PostgreSQL flows'
npm.cmd run build
```

Pentru fluxurile cu Flask și PostgreSQL reale, într-un terminal din `backend`:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe tests/browser_server.py
```

În alt terminal, din `frontend`:

```powershell
$env:RURIS_REAL_API = '1'
npm.cmd test -- real-flows.spec.js
```

Serverul temporar rulează pe 5201, frontendul de test pe 5174 și este oprit la
finalul execuției. Datele și directorul de documente se elimină. Pentru o a doua
execuție pornești din nou serverul. Inboxul de test este 8026, separat de 8025.

Pentru rularea obișnuită a testelor UI, elimină variabila după fluxurile reale:

```powershell
Remove-Item Env:RURIS_REAL_API
```

## Criterii de acceptare manuală

1. Cele trei roluri văd datele și acțiunile lor; apelul direct al unei operații
   nepermise este refuzat și în API.
2. Recepțiile 77 + 23 din 100 cresc stocul la 100, fără a confunda starea
   comercială „Confirmată” cu livrarea „Completă”.
3. Factura pentru 100 cu numai 77 acceptate rămâne blocată; fără aprobare nu se
   poate înregistra plata.
4. Marfa necomandată nu crește stocul până la acceptarea justificată.
5. Un duplicat neaprobat se poate anula cu motiv. Asocierile lui se eliberează,
   stocul rămâne neschimbat, fișierele și istoricul rămân accesibile.
6. O factură aprobată sau plătită nu poate fi anulată prin această operație.
7. Notificările personale păstrează mesajele trimise, chiar dacă situația a fost
   rezolvată ulterior. Clarificările curente și istoricul emailurilor sunt distincte.
8. După restaurare se pot folosi conturile și se pot descărca documentele, cu
   același conținut ca înainte de backup.

## Limite care nu trebuie prezentate drept funcții existente

- Stocul acoperă intrările acceptate; nu există încă ieșiri, retururi sau ajustări.
- Nu există avansuri, plăți parțiale, generare de ordine bancare sau integrare contabilă.
- Anularea din portal nu implementează fluxul de corecție pentru o factură deja aprobată/plătită.
- Formularul pornește dintr-o comandă; pentru documente cu mai multe comenzi,
  introducerea manuală și asocierile la recepții acoperă pozițiile compatibile ale aceluiași furnizor.
- Într-o zi fără curs BNR nu se alege automat altă dată.
- Instalarea Docker livrată este locală; HTTPS și operarea pe infrastructura firmei
  se configurează separat.
