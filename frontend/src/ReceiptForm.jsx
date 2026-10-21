import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, CircleAlert, LoaderCircle, Save } from 'lucide-react';
import { api } from './api.js';
import UnorderedReceiptForm from './UnorderedReceiptForm.jsx';

function localNow() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

async function confirmedOrders(signal) {
  const records = [];
  for (let page = 1; ; page += 1) {
    const data = await api(`/purchase-orders?page=${page}&per_page=100`, { signal });
    records.push(...data.orders);
    if (records.length >= data.total || !data.orders.length) break;
  }
  return records.filter((order) => order.status === 'CONFIRMED');
}

export default function ReceiptForm(props) {
  const [mode, setMode] = useState('ordered');
  const [busy, setBusy] = useState(false);
  return <><div className="receipt-mode" role="group" aria-label="Tip recepție">
    <button type="button" className={`button ${mode === 'ordered' ? 'button-primary' : 'button-secondary'}`} aria-pressed={mode === 'ordered'} disabled={busy} onClick={() => setMode('ordered')}>Din comandă</button>
    <button type="button" className={`button ${mode === 'unordered' ? 'button-primary' : 'button-secondary'}`} aria-pressed={mode === 'unordered'} disabled={busy} onClick={() => setMode('unordered')}>Fără comandă</button>
  </div>{mode === 'ordered' ? <OrderedReceiptForm {...props} onBusyChange={setBusy} /> : <UnorderedReceiptForm {...props} onBusyChange={setBusy} />}</>;
}

function OrderedReceiptForm({ onExpired, onCancel, onCreated, onBusyChange }) {
  const [choices, setChoices] = useState({ loading: true, orders: [] });
  const [attempt, setAttempt] = useState(0);
  const [orderId, setOrderId] = useState('');
  const [source, setSource] = useState(null);
  const [sourceAttempt, setSourceAttempt] = useState(0);
  const [quantities, setQuantities] = useState({});
  const [reference, setReference] = useState('');
  const [receivedAt, setReceivedAt] = useState(localNow);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const submitting = useRef(false);
  const errorBox = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    setChoices({ loading: true, orders: [] });
    confirmedOrders(controller.signal).then((orders) => {
      if (!controller.signal.aborted) setChoices({ loading: false, orders });
    }).catch((failure) => {
      if (failure.name === 'AbortError' || controller.signal.aborted) return;
      if ([401, 422].includes(failure.status)) onExpired();
      else setChoices({ loading: false, orders: [], error: failure.message });
    });
    return () => controller.abort();
  }, [attempt, onExpired]);

  useEffect(() => {
    setSource(null); setQuantities({}); setError('');
    if (!orderId) return;
    const controller = new AbortController();
    api(`/purchase-orders/${orderId}/delivery`, { signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted) setSource({ orderId, data: data.delivery });
    }).catch((failure) => {
      if (failure.name === 'AbortError' || controller.signal.aborted) return;
      if ([401, 422].includes(failure.status)) onExpired();
      else setSource({ orderId, error: failure.message });
    });
    return () => controller.abort();
  }, [orderId, sourceAttempt, onExpired]);

  useEffect(() => { if (error) errorBox.current?.focus(); }, [error]);
  const order = source?.orderId === orderId ? source.data : null;

  async function submit(event) {
    event.preventDefault();
    if (submitting.current || uncertain) return;
    setError('');
    if (!order || order.status !== 'CONFIRMED' || !choices.orders.some((item) => String(item.id) === orderId)) {
      setError('Selectează o comandă confirmată și deschisă.'); return;
    }
    const items = [];
    for (const line of order.items) {
      const value = (quantities[line.id] || '').trim().replace(',', '.');
      if (!value) continue;
      if (!/^[0-9]{1,15}(?:\.[0-9]{1,3})?$/.test(value) || !/[1-9]/.test(value)) {
        setError(`Poziția ${line.line_number}: cantitate pozitivă, cu maximum 3 zecimale.`); return;
      }
      items.push({ purchase_order_item_id: line.id, received_quantity: value });
    }
    if (!items.length) { setError('Completează cantitatea sosită pentru cel puțin un produs.'); return; }
    if (items.length > 100) { setError('O recepție poate avea maximum 100 de poziții.'); return; }
    if (!reference.trim()) { setError('Completează documentul de livrare.'); return; }
    const moment = new Date(receivedAt);
    if (!receivedAt || Number.isNaN(moment.getTime())) { setError('Completează data și ora recepției.'); return; }
    submitting.current = true; setSaving(true); onBusyChange(true);
    let keepModeLocked = false;
    try {
      const result = await api('/receipts', { method: 'POST', body: {
        purchase_order_id: Number(orderId), delivery_reference: reference.trim(), received_at: moment.toISOString(), items,
      } });
      onCreated(result.receipt);
    } catch (failure) {
      if ([401, 422].includes(failure.status)) onExpired();
      else if (failure.status === 0 || failure.status >= 500) {
        keepModeLocked = true;
        setUncertain(true); setError('Salvarea nu a putut fi confirmată. Verifică lista recepțiilor înainte să încerci din nou.');
      } else setError(failure.message);
    } finally { submitting.current = false; setSaving(false); onBusyChange(keepModeLocked); }
  }

  if (choices.loading) return <section className="panel feedback" role="status"><LoaderCircle className="spin" size={22} />Se încarcă…</section>;
  if (choices.error) return <section className="panel catalog-error"><p role="alert">{choices.error}</p><button className="button button-secondary" onClick={() => setAttempt((value) => value + 1)}>Încearcă din nou</button><button className="text-button" onClick={onCancel}>Înapoi la recepții</button></section>;
  return <form className="order-form receipt-form" onSubmit={submit}>
    {!choices.orders.length && <div className="notice" role="status">Nu există comenzi confirmate și deschise.</div>}
    {error && <div className="error-message" role="alert" ref={errorBox} tabIndex={-1}><CircleAlert size={18} />{error}</div>}
    <fieldset className="order-fields" disabled={saving || uncertain || !choices.orders.length}>
      <section className="panel order-header"><h2>Detalii recepție</h2><div className="user-form-grid receipt-header-grid">
        <div className="form-field"><label htmlFor="receipt-order">Comandă</label><select id="receipt-order" required value={orderId} onChange={(event) => setOrderId(event.target.value)}><option value="">Selectează comanda</option>{choices.orders.map((item) => <option key={item.id} value={item.id}>{item.number}</option>)}</select></div>
        <div className="form-field"><label htmlFor="receipt-reference">Document de livrare</label><input id="receipt-reference" required maxLength={120} value={reference} onChange={(event) => setReference(event.target.value)} /></div>
        <div className="form-field"><label htmlFor="receipt-date">Data și ora recepției</label><input id="receipt-date" type="datetime-local" required value={receivedAt} onChange={(event) => setReceivedAt(event.target.value)} /><small className="field-hint">Ora locală a browserului.</small></div>
      </div></section>
      {orderId && <section className="panel order-lines"><div className="panel-heading"><h2>Produse sosite</h2></div>
        {source?.orderId === orderId && source.error ? <div className="catalog-error"><p role="alert">{source.error}</p><button type="button" className="button button-secondary" onClick={() => setSourceAttempt((value) => value + 1)}>Reîncarcă produsele</button></div> : !order ? <div className="feedback" role="status">Se încarcă produsele…</div> : order.status !== 'CONFIRMED' ? <p className="order-empty" role="alert">Comanda nu mai este deschisă pentru recepție.</p> : <>
          <p className="receipt-hint">Completează doar cantitățile sosite. Ciorna nu modifică stocul.</p>
          {order.items.map((line) => <div className="order-line receipt-line" key={line.id}><div><strong>{line.line_number}. {line.description}</strong><p>Comandat: {line.quantity.replace('.', ',')} {line.unit} · Rest de livrat: {line.remaining_quantity.replace('.', ',')} {line.unit}</p></div><div className="form-field"><label htmlFor={`received-${line.id}`}>Cantitate sosită {line.line_number}</label><input id={`received-${line.id}`} inputMode="decimal" autoComplete="off" maxLength={19} value={quantities[line.id] || ''} onChange={(event) => setQuantities((current) => ({ ...current, [line.id]: event.target.value }))} /></div></div>)}
        </>}
      </section>}
    </fieldset>
    <div className="order-form-footer"><button type="button" className="button button-secondary" disabled={saving} onClick={onCancel}><ArrowLeft size={16} />{uncertain ? 'Vezi recepțiile' : 'Anulează'}</button><button type="submit" className="button button-primary" disabled={saving || uncertain || !order || order.status !== 'CONFIRMED' || !choices.orders.length}>{saving ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />}{saving ? 'Se salvează…' : 'Salvează ciorna'}</button></div>
  </form>;
}
