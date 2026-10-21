import { useEffect, useRef, useState } from 'react';
import { CircleAlert, LoaderCircle, RefreshCw } from 'lucide-react';
import { api } from './api.js';
import { parseQuantity, quantityDifference, quantityText } from './receiptQuantities.js';

async function openOrders(supplierId, signal) {
  const orders = [];
  for (let page = 1; ; page += 1) {
    const data = await api(`/purchase-orders?page=${page}&per_page=100`, { signal });
    orders.push(...data.orders.filter((order) => order.status === 'CONFIRMED' && order.supplier_id === supplierId));
    if (!data.orders.length || page * 100 >= data.total) return orders;
  }
}

function PendingLine({ line, role, orders, disabled, onWrite, onExpired }) {
  const [orderId, setOrderId] = useState('');
  const [source, setSource] = useState(null);
  const [itemId, setItemId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setSource(null); setItemId('');
    if (!orderId) return;
    const controller = new AbortController();
    api(`/purchase-orders/${orderId}/delivery`, { signal: controller.signal }).then((data) => {
      if (controller.signal.aborted) return;
      const items = data.delivery.items.filter((item) => item.unit === line.unit
        && (line.product_id === null || line.product_id === item.product_id)
        && parseQuantity(item.remaining_quantity)?.thousandths > 0n);
      setSource({ items });
      if (items.length === 1) setItemId(String(items[0].id));
    }).catch((failure) => {
      if (controller.signal.aborted || failure.name === 'AbortError') return;
      if ([401, 422].includes(failure.status)) onExpired();
      else setSource({ error: failure.message });
    });
    return () => controller.abort();
  }, [orderId, attempt, line.unit, line.product_id, onExpired]);

  function submit(action) {
    setError('');
    if (!reason.trim()) { setError('Completează observațiile deciziei.'); return; }
    if (role === 'ACHIZITII') {
      if (!source?.items?.some((item) => String(item.id) === itemId)) { setError('Selectează o poziție compatibilă din comandă.'); return; }
      onWrite(line.id, 'clarify', { purchase_order_item_id: Number(itemId), reason: reason.trim() });
    } else {
      const amount = parseQuantity(quantity);
      if (!amount || amount.thousandths === 0n || amount.thousandths > parseQuantity(line.pending_quantity).thousandths) {
        setError('Completează o cantitate pozitivă, de maximum 3 zecimale, în limita restului în așteptare.'); return;
      }
      onWrite(line.id, 'resolve', { action, quantity: amount.text, reason: reason.trim() });
    }
  }

  const hasCoverage = Boolean(line.pending_order_item_id || line.purchase_order_item_id);
  return <section className="pending-line" aria-label={`Clarificare poziția ${line.line_number}`}>
    <h4>{line.line_number}. {line.description}</h4>
    <p>În așteptare: <strong>{quantityText(line.pending_quantity)} {line.unit}</strong></p>
    <p className="field-hint">{hasCoverage ? `Acoperire: ${line.pending_order_number || 'comanda inițială'}${line.pending_product_name ? ` · ${line.pending_product_name}` : ''}` : 'Achizițiile trebuie să asocieze o comandă înainte de acceptare.'}</p>
    {error && <div className="error-message" role="alert">{error}</div>}
    <fieldset className="order-fields" disabled={disabled}>
      {role === 'ACHIZITII' ? <div className="pending-grid">
        <div className="form-field"><label htmlFor={`pending-order-${line.id}`}>Comandă pentru poziția {line.line_number}</label><select id={`pending-order-${line.id}`} value={orderId} onChange={(event) => setOrderId(event.target.value)}><option value="">Selectează comanda</option>{orders.map((order) => <option key={order.id} value={order.id}>{order.number}</option>)}</select></div>
        <div className="form-field"><label htmlFor={`pending-item-${line.id}`}>Produs comandat {line.line_number}</label><select id={`pending-item-${line.id}`} value={itemId} disabled={!source?.items?.length} onChange={(event) => setItemId(event.target.value)}><option value="">{orderId && !source ? 'Se încarcă…' : 'Selectează poziția'}</option>{source?.items?.map((item) => <option key={item.id} value={item.id}>{item.line_number}. {item.description} · rest {quantityText(item.remaining_quantity)} {item.unit}</option>)}</select></div>
      </div> : <div className="form-field"><label htmlFor={`pending-quantity-${line.id}`}>Cantitate de decis {line.line_number}</label><input id={`pending-quantity-${line.id}`} inputMode="decimal" maxLength={19} value={quantity} onChange={(event) => setQuantity(event.target.value)} /></div>}
      {source?.error && <div className="catalog-error"><p role="alert">{source.error}</p><button type="button" className="text-button" onClick={() => setAttempt((value) => value + 1)}>Reîncarcă pozițiile</button></div>}
      {source?.items?.length === 0 && <p className="field-hint">Comanda nu are poziții compatibile cu rest de livrat.</p>}
      {role === 'ACHIZITII' && !orders.length && <p className="field-hint">Creează și confirmă mai întâi o comandă pentru acest furnizor.</p>}
      <div className="form-field"><label htmlFor={`pending-reason-${line.id}`}>Observații decizie {line.line_number}</label><input id={`pending-reason-${line.id}`} maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /></div>
      <div className="document-actions">{role === 'ACHIZITII' ? <button type="button" className="button button-primary" onClick={() => submit('CLARIFY')}>Asociază comanda</button> : <>
        <button type="button" className="button button-primary" disabled={!hasCoverage} onClick={() => submit('ACCEPT')}>Acceptă cantitatea</button>
        <button type="button" className="button button-secondary" onClick={() => submit('REJECT')}>Respinge cantitatea</button>
      </>}</div>
    </fieldset>
  </section>;
}

export default function ReceiptPendingWorkflow({ receipt, role, onChanged, onBusyChange, onExpired, onReload }) {
  const pending = receipt.items.filter((line) => parseQuantity(line.pending_quantity)?.thousandths > 0n);
  const [choices, setChoices] = useState({ orders: [], loading: role === 'ACHIZITII' });
  const [attempt, setAttempt] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [requiresReload, setRequiresReload] = useState(false);
  const submitting = useRef(false);
  useEffect(() => {
    if (role !== 'ACHIZITII' || !pending.length) return;
    const controller = new AbortController();
    setChoices({ orders: [], loading: true });
    openOrders(receipt.supplier_id, controller.signal).then((orders) => {
      if (!controller.signal.aborted) setChoices({ orders });
    }).catch((failure) => {
      if (controller.signal.aborted || failure.name === 'AbortError') return;
      if ([401, 422].includes(failure.status)) onExpired();
      else setChoices({ orders: [], error: failure.message });
    });
    return () => controller.abort();
  }, [receipt.supplier_id, role, pending.length, attempt, onExpired]);

  async function write(itemId, operation, body) {
    if (submitting.current || requiresReload) return;
    submitting.current = true; setSaving(true); onBusyChange(true); setError('');
    try {
      const result = await api(`/receipts/${receipt.id}/items/${itemId}/${operation}`, { method: 'POST', body: { version: receipt.version, ...body } });
      onChanged(result.receipt, operation === 'clarify' ? 'Comanda a fost asociată. Marfa așteaptă decizia Depozitului.'
        : body.action === 'ACCEPT' ? 'Cantitatea a fost acceptată și adăugată în stoc.' : 'Cantitatea a fost respinsă.');
    } catch (failure) {
      if ([401, 422].includes(failure.status)) onExpired();
      else if (failure.status === 0 || failure.status >= 500) {
        setError('Rezultatul nu a putut fi confirmat. Actualizează datele înainte de o nouă încercare.'); setRequiresReload(true);
      } else { setError(failure.message); setRequiresReload(failure.status === 409); }
    } finally { submitting.current = false; setSaving(false); onBusyChange(false); }
  }

  const acceptances = receipt.items.flatMap((line) => (line.acceptances || []).map((acceptance) => ({ ...acceptance, original_line: line.line_number })));
  return <>
    {acceptances.length > 0 && <section className="receipt-acceptances" aria-label="Acceptări ulterioare"><h3>Acceptări ulterioare</h3><div className="table-scroll"><table><thead><tr><th>Poziție sosire</th><th>Produs identificat</th><th>Comandă</th><th>Acceptat</th><th>Unitate</th></tr></thead><tbody>{acceptances.map((item) => <tr key={item.id}><td>{item.original_line}</td><td>{item.product_name}</td><td>{item.order_number}</td><td>{quantityText(item.accepted_quantity)}</td><td>{item.unit}</td></tr>)}</tbody></table></div></section>}
    {pending.length > 0 && <section className="receipt-pending" aria-label="Cantități în așteptare"><h3>De clarificat</h3>
      {error && <div className="error-message" role="alert"><CircleAlert size={18} />{error}</div>}
      {saving && <p role="status"><LoaderCircle className="spin" size={16} /> Se salvează…</p>}
      {requiresReload && <button type="button" className="button button-secondary" onClick={onReload}><RefreshCw size={16} />Actualizează datele</button>}
      {['ACHIZITII', 'DEPOZIT'].includes(role) ? choices.loading ? <p role="status">Se încarcă comenzile…</p> : choices.error ? <div className="catalog-error"><p role="alert">{choices.error}</p><button type="button" className="button button-secondary" onClick={() => setAttempt((value) => value + 1)}>Reîncarcă comenzile</button></div> : pending.map((line) => <PendingLine key={line.id} line={line} role={role} orders={choices.orders} disabled={saving || requiresReload} onWrite={write} onExpired={onExpired} />)
        : <p className="field-hint">Cantitățile în așteptare nu sunt disponibile pentru facturare.</p>}
    </section>}
    <ReceiptHistory id={receipt.id} version={receipt.version} onExpired={onExpired} />
  </>;
}

function ReceiptHistory({ id, version, onExpired }) {
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true });
    api(`/receipts/${id}/history?page=${page}&per_page=10`, { signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted) setState({ data });
    }).catch((failure) => {
      if (controller.signal.aborted || failure.name === 'AbortError') return;
      if ([401, 422].includes(failure.status)) onExpired();
      else setState({ error: failure.message });
    });
    return () => controller.abort();
  }, [id, version, page, attempt, onExpired]);

  function eventText(event) {
    const prefix = event.line_number ? `Poziția ${event.line_number}: ` : '';
    if (event.action === 'ACCEPT' || event.action === 'REJECT') {
      return `${prefix}${event.action === 'ACCEPT' ? 'acceptate' : 'respinse'} ${quantityDifference(event.before.pending_quantity, event.after.pending_quantity)} ${event.after.unit}${event.order_number ? ` · ${event.order_number}` : ''}`;
    }
    const labels = { CLARIFY: 'comandă asociată', CONFIRM: 'recepție confirmată', UPDATE: 'date actualizate', CREATE: event.is_acceptance ? 'acceptare înregistrată separat' : event.line_number ? 'sosire înregistrată' : 'recepție creată' };
    return prefix + (labels[event.action] || 'operație înregistrată') + (event.order_number ? ` · ${event.order_number}` : '');
  }

  return <section className="receipt-history" aria-label="Istoric recepție"><h3>Istoric</h3>
    {state.loading ? <p role="status">Se încarcă istoricul…</p> : state.error ? <div className="catalog-error"><p role="alert">{state.error}</p><button type="button" className="button button-secondary" onClick={() => setAttempt((value) => value + 1)}>Reîncarcă istoricul</button></div> : <>
      <ol className="receipt-history-list">{(state.data?.events || []).map((event) => <li key={event.id}><strong>{eventText(event)}</strong><p>{event.actor_name} · {new Intl.DateTimeFormat('ro-RO', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(event.created_at))}</p>{event.reason && <p>{event.reason}</p>}</li>)}</ol>
      {state.data?.total > 10 && <div className="pagination"><span>Pagina {page} din {Math.ceil(state.data.total / 10)}</span><div><button type="button" className="button button-secondary" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Mai recente</button><button type="button" className="button button-secondary" disabled={page * 10 >= state.data.total} onClick={() => setPage((value) => value + 1)}>Mai vechi</button></div></div>}
    </>}
  </section>;
}
