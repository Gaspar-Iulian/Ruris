import { useEffect, useRef, useState } from 'react';
import { CircleAlert, LoaderCircle, RefreshCw } from 'lucide-react';
import { api } from './api.js';
import { quantityText } from './receiptQuantities.js';
import InvoiceForm from './InvoiceForm.jsx';
import DeclaredTotals, { emptyTotals, readTotals } from './DeclaredTotals.jsx';
import { LineAmounts } from './AmountsPreview.jsx';
import { calculateTotals } from './amounts.js';

const display = (value) => String(value ?? '—').replace('.', ',');
const issueDetails = (issue) => issue.code === 'QUANTITY_NOT_COVERED'
  ? issue.details.replace(/\b\d+\.\d{3}\b/g, (value) => quantityText(value)) : issue.details;
const differenceLabels = { PRICE: 'Preț diferit de comandă', VAT: 'TVA diferit de comandă', CURRENCY: 'Monedă diferită de comandă', UNIT: 'Unitate diferită' };
const roleLabels = { ACHIZITII: 'Achiziții', DEPOZIT: 'Depozit', CONTABILITATE: 'Contabilitate' };

function quantity(value) {
  const normalized = value.trim().replace(',', '.');
  if (!/^[0-9]{1,15}(?:\.[0-9]{1,3})?$/.test(normalized)) return null;
  const [whole, decimals = ''] = normalized.split('.');
  return { text: normalized, scaled: BigInt(whole) * 1000n + BigInt(decimals.padEnd(3, '0')) };
}

function textQuantity(value) {
  return quantityText(`${value / 1000n}.${String(value % 1000n).padStart(3, '0')}`, '.');
}

function localNow() {
  const moment = new Date();
  return new Date(moment.getTime() - moment.getTimezoneOffset() * 60000).toISOString().slice(0, 23);
}

function proposal(data) {
  const remainingByReceipt = new Map();
  const proposed = {};
  for (const line of data.items) {
    let remaining = quantity(line.remaining_quantity).scaled;
    for (const candidate of line.candidates) {
      if (!candidate.eligible || remaining === 0n) continue;
      const capacity = remainingByReceipt.has(candidate.receipt_item_id) ? remainingByReceipt.get(candidate.receipt_item_id) : quantity(candidate.available_quantity).scaled;
      const used = remaining < capacity ? remaining : capacity;
      if (used > 0n) proposed[`${line.id}:${candidate.receipt_item_id}`] = textQuantity(used);
      remaining -= used; remainingByReceipt.set(candidate.receipt_item_id, capacity - used);
    }
  }
  return proposed;
}

export default function InvoiceWorkflow({ invoice, onChanged, onExpired, onBusyChange, onEditingChange }) {
  const [state, setState] = useState({ loading: true });
  const [revision, setRevision] = useState(0);
  const [quantities, setQuantities] = useState({});
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [requiresReload, setRequiresReload] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editingTotals, setEditingTotals] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [declaredTotals, setDeclaredTotals] = useState(emptyTotals);
  const [paymentReference, setPaymentReference] = useState('');
  const [paidAt, setPaidAt] = useState(localNow);
  const submitting = useRef(false);
  const errorBox = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true });
    api(`/invoices/${invoice.id}/matching`, { signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted) { setState({ data }); setQuantities({}); }
    }).catch((failure) => {
      if (failure.name === 'AbortError' || controller.signal.aborted) return;
      if ([401, 422].includes(failure.status)) onExpired();
      else setState({ error: failure.message });
    });
    return () => controller.abort();
  }, [invoice.id, invoice.version, revision, onExpired]);
  useEffect(() => { if (error) errorBox.current?.focus(); }, [error]);
  useEffect(() => { if (invoice.status === 'APPROVED') setPaidAt(localNow()); }, [invoice.status]);
  useEffect(() => { onEditingChange?.(editing || editingTotals); }, [editing, editingTotals, onEditingChange]);

  function setWorking(value) { submitting.current = value; setBusy(value); onBusyChange(value); }

  async function refresh() {
    if (submitting.current) return;
    setWorking(true); setError('');
    try {
      const data = await api(`/invoices/${invoice.id}/matching`);
      setState({ data }); setQuantities({}); setRequiresReload(false); onChanged(data.invoice);
      setRevision((value) => value + 1);
    } catch (failure) {
      if ([401, 422].includes(failure.status)) onExpired();
      else setError(failure.message);
    } finally { setWorking(false); }
  }

  async function perform(action, payload, message, needsReason = true, verifyAfter = false, method = 'POST') {
    if (submitting.current || requiresReload) return;
    if (editingTotals && action !== 'declared-totals') { setError('Salvează sau anulează editarea totalurilor înainte de altă operație.'); return; }
    if (needsReason && !reason.trim()) { setError('Completează observațiile operației.'); return; }
    setWorking(true); setError(''); setNotice('');
    try {
      const result = await api(`/invoices/${invoice.id}/${action}`, { method, body: { version: state.data.invoice.version, ...payload, ...(needsReason ? { reason: reason.trim() } : {}) } });
      if (verifyAfter) await api(`/invoices/${invoice.id}/verify`, { method: 'POST', body: { version: result.version } });
      const data = await api(`/invoices/${invoice.id}/matching`);
      setState({ data }); setQuantities({}); onChanged(data.invoice);
      setNotice(verifyAfter ? (data.invoice.status === 'VERIFIED' ? 'Asocierile au fost salvate. Factura este verificată.' : 'Asocierile au fost salvate. Factura are în continuare blocaje.') : message);
      if (action === 'declared-totals') setEditingTotals(false);
      if (action === 'cancel') { setCancelling(false); setCancelReason(''); }
    } catch (failure) {
      if ([401, 422].includes(failure.status)) onExpired();
      else if (failure.status === 0 || failure.status >= 500) {
        setError('Rezultatul operației nu a putut fi verificat. Actualizează factura înainte să încerci din nou.'); setRequiresReload(true);
      } else { setError(failure.message); setRequiresReload(failure.status === 409); }
    } finally { setWorking(false); }
  }

  function suggest() {
    const proposed = proposal(state.data);
    setQuantities(proposed); setError('');
    setNotice(Object.keys(proposed).length ? 'Propunerea este completată. Verifică și salvează asocierile.' : 'Nu există cantități compatibile disponibile pentru asociere.');
  }

  function allocate(verifyAfter = false) {
    const selected = verifyAfter && !Object.values(quantities).some((value) => value.trim()) ? proposal(state.data) : quantities;
    const items = [];
    for (const line of state.data.items) {
      for (const candidate of line.candidates) {
        const raw = selected[`${line.id}:${candidate.receipt_item_id}`] || '';
        if (!raw.trim()) continue;
        const parsed = quantity(raw);
        if (!parsed || parsed.scaled <= 0n || !candidate.eligible) { setError('Cantitățile asociate trebuie să fie pozitive, cu maximum 3 zecimale.'); return; }
        items.push({ invoice_item_id: line.id, receipt_item_id: candidate.receipt_item_id, quantity: parsed.text });
      }
    }
    if (!items.length) { setError('Completează cel puțin o cantitate de asociat.'); return; }
    if (items.length > 100) { setError('Salvează maximum 100 de asocieri într-o operație.'); return; }
    perform('allocations', { items }, 'Asocierile au fost salvate.', true, verifyAfter);
  }

  function pay() {
    const moment = new Date(paidAt);
    if (!paymentReference.trim() || !paidAt || Number.isNaN(moment.getTime())) { setError('Completează referința și data plății.'); return; }
    perform('pay', { payment_reference: paymentReference.trim(), paid_at: moment.toISOString() }, 'Plata a fost înregistrată.');
  }

  function cancelInvoice() {
    if (!cancelReason.trim()) { setError('Completează motivul anulării.'); return; }
    perform('cancel', { reason: cancelReason.trim() }, 'Factura a fost anulată. Asocierile au fost eliberate.', false);
  }

  function saveTotals() {
    try {
      const parsed = readTotals(declaredTotals);
      if (parsed === null) { setError('Completează netul, TVA și totalul de pe document.'); return; }
      perform('declared-totals', { declared_totals: parsed }, 'Totalurile au fost salvate. Verifică din nou factura.', true, false, 'PATCH');
    } catch (failure) { setError(failure.message); }
  }

  if (state.loading) return <div className="feedback" role="status"><LoaderCircle className="spin" size={22} />Se încarcă factura…</div>;
  if (state.error) return <div className="catalog-error"><p role="alert">{state.error}</p><button className="button button-secondary" onClick={() => setRevision((value) => value + 1)}>Reîncarcă factura</button></div>;
  const data = state.data;
  const current = data.invoice;
  const mutable = ['DRAFT', 'BLOCKED', 'VERIFIED'].includes(current.status);
  const canAssociate = mutable && data.items.some((line) => quantity(line.remaining_quantity).scaled > 0n && line.candidates.some((candidate) => candidate.eligible && quantity(candidate.available_quantity).scaled > 0n));
  if (editing) return <InvoiceForm key={`${current.id}-${current.version}`} initialInvoice={current} onExpired={onExpired} onBusyChange={onBusyChange} onCancel={() => { setEditing(false); refresh(); }} onCreated={(updated) => { setEditing(false); onChanged(updated); setNotice('Factura a fost corectată. Este necesară verificarea.'); }} />;

  return <section className="invoice-workflow" aria-label="Procesare factură">
    {current.status === 'CANCELLED' && <div className="notice" role="status"><strong>Factura este anulată.</strong><p>{current.cancellation_reason}</p><p>Anulată la {new Date(current.cancelled_at).toLocaleString('ro-RO')}. Documentul rămâne disponibil pentru consultare.</p></div>}
    <div className="invoice-summary"><span>Net: <strong>{display(current.net_amount)} {current.currency}</strong></span><span>TVA: <strong>{display(current.vat_amount)} {current.currency}</strong></span><span>Total: <strong>{display(current.total_amount)} {current.currency}</strong></span></div>
    <section className="invoice-totals-comparison" aria-label="Comparare totaluri"><h3>Totaluri factură ({current.currency})</h3>
      {current.declared_totals ? <div className="table-scroll"><table><thead><tr><th>Sumă</th><th>Din poziții</th><th>Pe document</th><th>Diferență</th></tr></thead><tbody>{[['net_amount', 'Net'], ['vat_amount', 'TVA'], ['total_amount', 'Total']].map(([key, label]) => <tr key={key}><th scope="row">{label}</th><td>{display(current[key])}</td><td>{display(current.declared_totals[key])}</td><td className={current.totals_difference?.[key] !== '0.00' ? 'candidate-difference' : ''}>{display(current.totals_difference?.[key])}</td></tr>)}</tbody></table></div> : <p className="notice">{mutable ? 'Totalurile de pe document nu sunt completate. Completează-le înainte de verificare.' : 'Totalurile de pe document nu au fost completate.'}</p>}
    </section>
    {current.total_ron !== null && current.total_ron !== undefined && <div className="notice">Total în RON: <strong>{display(current.total_ron)}</strong>{current.exchange_rate_source === 'BNR' && <> · Curs BNR: {display(current.exchange_rate_value)} · Data cursului: {current.exchange_rate_date}</>}</div>}
    {mutable && current.currency === 'EUR' && !current.total_ron && <p className="field-hint">Cursul BNR din {current.invoice_date} se preia la verificare. Conversia necesită un curs publicat pentru această dată.</p>}
    {current.exchange_rate_source === 'BNR' && <p className="field-hint"><a href={`https://curs.bnr.ro/files/xml/years/nbrfxrates${current.exchange_rate_date.slice(0, 4)}.xml`} target="_blank" rel="noreferrer">Sursa cursului BNR</a></p>}
    {notice && <div className="notice success-notice" role="status">{notice}</div>}
    {error && <div className="error-message" role="alert" tabIndex={-1} ref={errorBox}><CircleAlert size={18} />{error}</div>}
    {requiresReload && <button className="button button-secondary" disabled={busy} onClick={refresh}><RefreshCw size={16} />Actualizează factura</button>}
    {data.issues.length > 0 && <section className="invoice-issues" aria-label="Blocaje factură"><h3>De clarificat</h3>{data.issues.map((issue) => <div key={issue.id} className="invoice-issue"><p>{issueDetails(issue)}</p><small>Responsabil: {roleLabels[issue.responsible_role] || issue.responsible_role}</small></div>)}{canAssociate && <p className="invoice-issue">Există marfă disponibilă, dar încă neasociată. Completează observațiile și apasă „Asociază și verifică”.</p>}</section>}
    <fieldset className="order-fields" disabled={busy || requiresReload}>
      {mutable && <div className="workflow-actions"><button className="button button-secondary" onClick={() => { setEditingTotals((value) => !value); setDeclaredTotals(current.declared_totals || emptyTotals()); setError(''); }}>{editingTotals ? 'Anulează totalurile' : 'Editează totalurile'}</button>{data.issues.some((issue) => ['EXCHANGE_RATE_MISSING', 'EXCHANGE_RATE_NOT_PUBLISHED'].includes(issue.code)) && <button className="button button-secondary" onClick={() => perform('verify', {}, 'Cursul și factura au fost verificate din nou.', false)}>Reîncearcă preluarea cursului</button>}</div>}
      {editingTotals && <><DeclaredTotals values={declaredTotals} onChange={setDeclaredTotals} currency={current.currency} calculated={calculateTotals(current.items || [])} /><button className="button button-primary" onClick={saveTotals}>Salvează totalurile</button></>}
      {mutable && <><div className="workflow-actions"><button className="button button-secondary" onClick={suggest}>Propune asocierea</button>{data.allocations.length === 0 && <button className="button button-secondary" onClick={() => { setError(''); setEditing(true); }}>Corectează factura</button>}</div><p className="field-hint">Asociază doar cantitățile acceptate. Propunerea se salvează separat.</p></>}
      {data.items.map((line) => <section className="invoice-match-line" key={line.id} aria-label={`Poziția facturii ${line.line_number}`}><h3>{line.line_number}. {line.description}</h3><p className="field-hint">Facturat: {quantityText(line.quantity)} {line.unit} · Asociat: {quantityText(line.allocated_quantity)} · Neacoperit: {quantityText(line.remaining_quantity)} · Preț: {display(line.unit_price)} {current.currency} · TVA: {display(line.vat_rate)}%</p>
        <LineAmounts line={line} currency={current.currency} />
        {mutable && (line.candidates.length ? line.candidates.map((candidate) => <div className="invoice-candidate" key={candidate.receipt_item_id}><div><strong>{candidate.receipt_number} · {candidate.order_number}</strong><p>Acceptat: {quantityText(candidate.accepted_quantity)} · Asociat facturilor: {quantityText(candidate.allocated_quantity)} · Disponibil: {quantityText(candidate.available_quantity)}</p>{candidate.differences.length > 0 && <p className="candidate-difference">{candidate.differences.map((code) => differenceLabels[code]).join(' · ')}. Comandă: {display(candidate.order_unit_price)} {candidate.order_currency}, TVA {display(candidate.order_vat_rate)}%.</p>}</div><div className="form-field"><label htmlFor={`allocation-${line.id}-${candidate.receipt_item_id}`}>De asociat · poziția {line.line_number} · {candidate.receipt_number}</label><input id={`allocation-${line.id}-${candidate.receipt_item_id}`} inputMode="decimal" maxLength={19} disabled={!candidate.eligible || quantity(candidate.available_quantity).scaled === 0n} value={quantities[`${line.id}:${candidate.receipt_item_id}`] || ''} onChange={(event) => setQuantities((previous) => ({ ...previous, [`${line.id}:${candidate.receipt_item_id}`]: event.target.value }))} /></div></div>) : <p className="notice">Nu există recepții confirmate cu marfă acceptată pentru această poziție.</p>)}
      </section>)}
      {data.allocations.length > 0 && <section aria-label="Asocieri active"><h3>Asocieri active</h3>{data.allocations.map((allocation) => <div className="active-allocation" key={allocation.id}><span>Poziția {data.items.find((line) => line.id === allocation.invoice_item_id)?.line_number} · {quantityText(allocation.quantity)} · {allocation.receipt_number || 'Recepție indisponibilă'} · {allocation.order_number || '—'}</span>{mutable && <button className="text-button" aria-label={`Eliberează asocierea #${allocation.id}`} onClick={() => perform('allocations/release', { allocation_ids: [allocation.id] }, 'Asocierea a fost eliberată.')}>Eliberează</button>}</div>)}</section>}
      {(mutable || current.status === 'APPROVED') && <div className="form-field workflow-reason"><label htmlFor="invoice-operation-reason">Observații operație</label><input id="invoice-operation-reason" maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /></div>}
      {mutable && <div className="workflow-actions"><button className="button button-secondary" onClick={() => allocate()}>Salvează asocierile</button><button className="button button-primary" onClick={() => canAssociate ? allocate(true) : perform('verify', {}, 'Verificarea facturii s-a încheiat.', false)}>{canAssociate ? 'Asociază și verifică' : 'Verifică factura'}</button>{current.status === 'VERIFIED' && <button className="button button-primary" onClick={() => perform('approve', {}, 'Factura a fost aprobată.')}>Aprobă factura</button>}</div>}
      {mutable && !editingTotals && !cancelling && <div className="document-actions"><button type="button" className="button button-secondary" onClick={() => { setCancelling(true); setCancelReason(''); setError(''); }}>Anulează factura</button></div>}
      {mutable && cancelling && <section className="invoice-cancellation" aria-label="Anulare factură"><h3>Anulare factură</h3><p className="field-hint">Factura rămâne în istoric. Asocierile active vor fi eliberate, iar cantitățile vor redeveni disponibile.</p>
        <div className="form-field"><label htmlFor="invoice-cancel-reason">Motivul anulării</label><input id="invoice-cancel-reason" maxLength={1000} value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} /></div>
        <div className="workflow-actions"><button type="button" className="button button-primary" onClick={cancelInvoice}>Confirmă anularea</button><button type="button" className="button button-secondary" onClick={() => setCancelling(false)}>Păstrează factura</button></div>
      </section>}
      {current.status === 'APPROVED' && <section className="payment-form" aria-label="Înregistrare plată"><h3>Înregistrează plata</h3><div className="user-form-grid"><div className="form-field"><label htmlFor="invoice-payment-reference">Referință plată</label><input id="invoice-payment-reference" maxLength={120} value={paymentReference} onChange={(event) => setPaymentReference(event.target.value)} /></div><div className="form-field"><label htmlFor="invoice-paid-at">Data și ora plății</label><input id="invoice-paid-at" type="datetime-local" step="0.001" value={paidAt} onChange={(event) => setPaidAt(event.target.value)} /></div></div><button className="button button-primary" onClick={pay}>Înregistrează plata</button></section>}
      {current.status === 'PAID' && <div className="notice" role="status">Plată înregistrată: <strong>{current.payment_reference}</strong> · {new Date(current.paid_at).toLocaleString('ro-RO')}</div>}
    </fieldset>
    {busy && <p className="field-hint" role="status">Se procesează…</p>}
  </section>;
}
