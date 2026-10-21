import { useEffect, useState } from 'react';
import { ChevronDown, History, LoaderCircle } from 'lucide-react';
import { api } from './api.js';
import { quantityText } from './receiptQuantities.js';

const fields = { description: 'Produs', quantity: 'Cantitate', unit: 'Unitate', unit_price: 'Preț unitar', vat_rate: 'TVA (%)',
  cancellation_reason: 'Motivul anulării', cancelled_at: 'Momentul anulării',
  expected_date: 'Termen', status: 'Stare', currency: 'Monedă', invoice_date: 'Data facturii', due_date: 'Scadență',
  net_amount: 'Net', vat_amount: 'TVA', total_amount: 'Total', total_ron: 'Total RON', number: 'Număr', series: 'Serie',
  declared_totals: 'Totaluri de pe document', totals_difference: 'Diferențe de sume',
  original_name: 'Fișier', size_bytes: 'Dimensiune (octeți)', upload_reason: 'Observații fișier', withdrawal_reason: 'Motivul retragerii',
  exchange_rate_value: 'Curs', exchange_rate_date: 'Data cursului', exchange_rate_source: 'Sursa cursului',
  details: 'Detalii', responsible_role: 'Responsabil', resolution: 'Rezolvare', paid_at: 'Momentul plății',
  approved_at: 'Momentul aprobării', confirmed_at: 'Momentul confirmării', payment_reference: 'Referință plată' };
const values = { DRAFT: 'Ciornă', CONFIRMED: 'Confirmată', CLOSED: 'Închisă', CANCELLED: 'Anulată', BLOCKED: 'Blocată',
  VERIFIED: 'Verificată', APPROVED: 'Aprobată', PAID: 'Plătită', ACTIVE: 'Activă', RELEASED: 'Eliberată',
  WITHDRAWN: 'Retras',
  ACHIZITII: 'Achiziții', DEPOZIT: 'Depozit', CONTABILITATE: 'Contabilitate', RESOLVED: 'Rezolvat', SUPERSEDED: 'Închis după modificare' };

function title(event) {
  const after = event.after || {};
  if (event.entity_type === 'invoices' && event.action === 'CANCEL') return 'Factură anulată';
  if (event.entity_type === 'attachments') return ({ UPLOAD: 'Fișier atașat', WITHDRAW: 'Fișier retras', DOWNLOAD: 'Descărcare pregătită' })[event.action] || 'Document atașat';
  if (event.entity_type === 'invoice_allocations') return event.action === 'RELEASE' ? 'Asociere eliberată' : 'Asociere la recepție';
  if (event.entity_type === 'invoice_issues') return ({ OPEN: 'Blocaj deschis', UPDATE: 'Blocaj actualizat', RESOLVE: 'Blocaj rezolvat', SUPERSEDE: 'Blocaj închis după modificare' })[event.action] || 'Blocaj actualizat';
  if (event.action === 'VERIFY') return `Factură verificată: ${values[after.status] || after.status}`;
  return ({ CREATE: event.line_number ? 'Poziție adăugată' : 'Document creat', UPDATE: 'Date actualizate', DELETE: 'Poziție eliminată',
    CONFIRM: 'Comandă confirmată', APPROVE: 'Factură aprobată', PAY: 'Plată înregistrată' })[event.action] || 'Operație înregistrată';
}

function display(value, field) {
  if (value === null || value === undefined || value === '') return '—';
  if (field === 'quantity') return quantityText(value);
  if (typeof value === 'object') return ['net_amount', 'vat_amount', 'total_amount'].map((key) => `${fields[key]}: ${display(value[key])}`).join(' · ');
  return Object.hasOwn(values, String(value)) ? values[value]
    : (/^\d+(\.\d+)?$/.test(String(value)) ? String(value).replace('.', ',') : String(value));
}

export default function DocumentHistory({ kind, id, version, onExpired }) {
  const [open, setOpen] = useState(false);
  return <section className="document-history" aria-label={kind === 'order' ? 'Istoric comandă' : 'Istoric factură'}>
    <button type="button" className="history-toggle" aria-expanded={open} onClick={() => setOpen((value) => !value)}><History size={17} />Istoric<ChevronDown size={16} /></button>
    {open && <HistoryEntries key={`${id}-${version}`} kind={kind} id={id} onExpired={onExpired} />}
  </section>;
}

function HistoryEntries({ kind, id, onExpired }) {
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true });
    api(`/${kind === 'order' ? 'purchase-orders' : 'invoices'}/${id}/history?page=${page}&per_page=10`, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setState({ data }); })
      .catch((failure) => {
        if (controller.signal.aborted || failure.name === 'AbortError') return;
        if ([401, 422].includes(failure.status)) onExpired();
        else setState({ error: failure.message });
      });
    return () => controller.abort();
  }, [kind, id, page, attempt, onExpired]);
  if (state.loading) return <p className="field-hint" role="status"><LoaderCircle size={16} className="spin" /> Se încarcă istoricul…</p>;
  if (state.error) return <div className="catalog-error"><p role="alert">{state.error}</p><button type="button" className="button button-secondary" onClick={() => setAttempt((value) => value + 1)}>Reîncarcă istoricul</button></div>;
  const data = state.data;
  return <>
    {!data.events?.length ? <p className="field-hint">Nu există operații de afișat.</p> : <ol className="document-history-list">{data.events.map((event) => {
      const changes = Object.keys(fields).filter((field) => JSON.stringify(event.before?.[field] ?? null) !== JSON.stringify(event.after?.[field] ?? null));
      return <li key={event.id}><strong>{event.line_number ? `Poziția ${event.line_number}: ` : ''}{title(event)}</strong>
        <p>{event.actor_name} · {new Intl.DateTimeFormat('ro-RO', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(event.created_at))}</p>
        {event.reason && <p>{event.reason}</p>}
        {changes.length > 0 && <details className="history-changes"><summary>Modificări</summary><dl>{changes.map((field) => <div key={field}><dt>{fields[field]}</dt><dd>{event.before && <>{display(event.before[field], field)} → </>}{display(event.after?.[field], field)}</dd></div>)}</dl></details>}
      </li>;
    })}</ol>}
    {data.total > 10 && <div className="pagination"><span>Pagina {page} din {Math.ceil(data.total / 10)}</span><div><button type="button" className="button button-secondary" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Mai recente</button><button type="button" className="button button-secondary" disabled={page * 10 >= data.total} onClick={() => setPage((value) => value + 1)}>Mai vechi</button></div></div>}
  </>;
}
