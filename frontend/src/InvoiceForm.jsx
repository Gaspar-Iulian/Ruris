import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, CircleAlert, LoaderCircle, Plus, Save, Trash2 } from 'lucide-react';
import { api } from './api.js';
import DeclaredTotals, { emptyTotals, readTotals } from './DeclaredTotals.jsx';

const newLine = () => ({ key: crypto.randomUUID(), product_id: '', quantity: '1', unit_price: '', vat_rate: '0' });

async function catalog(path, key, signal, activeOnly = true) {
  const records = [];
  for (let page = 1; ; page += 1) {
    const data = await api(`${path}?page=${page}&per_page=100`, { signal });
    records.push(...data[key]);
    if (records.length >= data.total || !data[key].length) break;
  }
  return activeOnly ? records.filter((record) => record.is_active) : records;
}

function decimal(value, scale, digits, positive = false) {
  const normalized = value.trim().replace(',', '.');
  if (!new RegExp(`^[0-9]{1,${digits}}(?:\\.[0-9]{1,${scale}})?$`).test(normalized)) return null;
  return positive && !/[1-9]/.test(normalized) ? null : normalized;
}

export default function InvoiceForm({ onExpired, onCancel, onCreated, initialInvoice = null, onBusyChange = () => {} }) {
  const editing = initialInvoice !== null;
  const [mode, setMode] = useState(editing ? 'manual' : 'order');
  const [orderId, setOrderId] = useState('');
  const [source, setSource] = useState(null);
  const [sourceAttempt, setSourceAttempt] = useState(0);
  const [supplierId, setSupplierId] = useState(initialInvoice ? String(initialInvoice.supplier_id) : '');
  const [series, setSeries] = useState(initialInvoice?.series || '');
  const [number, setNumber] = useState(initialInvoice?.number || '');
  const [invoiceDate, setInvoiceDate] = useState(initialInvoice?.invoice_date || '');
  const [dueDate, setDueDate] = useState(initialInvoice?.due_date || '');
  const [currency, setCurrency] = useState(initialInvoice?.currency || 'RON');
  const [declaredTotals, setDeclaredTotals] = useState(() => initialInvoice?.declared_totals || emptyTotals());
  const [lines, setLines] = useState(() => initialInvoice ? initialInvoice.items.map((item) => ({ ...newLine(), ...item, product_id: String(item.product_id) })) : []);
  const [reason, setReason] = useState('');
  const [choices, setChoices] = useState({ loading: true, suppliers: [], products: [], orders: [] });
  const [attempt, setAttempt] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const submitting = useRef(false);
  const errorBox = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    setChoices({ loading: true, suppliers: [], products: [], orders: [] });
    Promise.all([catalog('/suppliers', 'suppliers', controller.signal), catalog('/products', 'products', controller.signal), catalog('/purchase-orders', 'orders', controller.signal, false)])
      .then(([suppliers, products, orders]) => {
        if (!controller.signal.aborted) setChoices({ loading: false, suppliers, products, orders: orders.filter((order) => ['CONFIRMED', 'CLOSED'].includes(order.status)) });
      }).catch((failure) => {
        if (failure.name === 'AbortError' || controller.signal.aborted) return;
        if ([401, 422].includes(failure.status)) onExpired();
        else setChoices({ loading: false, suppliers: [], products: [], error: failure.message });
      });
    return () => controller.abort();
  }, [attempt, onExpired]);
  useEffect(() => {
    if (mode !== 'order' || !orderId) return;
    const controller = new AbortController();
    setSource(null); setLines([]); setError('');
    api(`/purchase-orders/${orderId}/invoicing`, { signal: controller.signal }).then(({ order }) => {
      if (controller.signal.aborted) return;
      setSource({ id: orderId, order }); setSupplierId(String(order.supplier_id)); setCurrency(order.currency);
      setLines(order.items.map((item) => ({ ...newLine(), product_id: String(item.product_id), quantity: item.quantity,
        unit_price: item.unit_price, vat_rate: item.vat_rate, purchase_order_item_id: item.id, source: item })));
    }).catch((failure) => {
      if (controller.signal.aborted || failure.name === 'AbortError') return;
      if ([401, 422].includes(failure.status)) onExpired();
      else setSource({ id: orderId, error: failure.message });
    });
    return () => controller.abort();
  }, [mode, orderId, sourceAttempt, onExpired]);
  useEffect(() => { if (error) errorBox.current?.focus(); }, [error]);

  function changeMode(value) {
    setMode(value); setOrderId(''); setSource(null); setSupplierId(''); setCurrency('RON');
    setLines(value === 'manual' ? [newLine()] : []); setError('');
  }

  function changeLine(key, field, value) {
    setLines((current) => current.map((line) => line.key === key ? { ...line, [field]: value,
      ...(field === 'product_id' ? { purchase_order_item_id: null, source: null } : {}) } : line));
  }

  async function submit(event) {
    event.preventDefault();
    if (submitting.current || uncertain) return;
    setError('');
    if (editing && !reason.trim()) { setError('Completează motivul corectării.'); return; }
    if (mode === 'order' && (source?.id !== orderId || !source?.order)) { setError('Selectează o comandă și așteaptă încărcarea pozițiilor.'); return; }
    if (!choices.suppliers.some((supplier) => String(supplier.id) === supplierId)) { setError('Selectează un furnizor activ.'); return; }
    const normalizedSeries = series.trim().toUpperCase();
    const normalizedNumber = number.trim().toUpperCase();
    const reference = /^[A-Z0-9][A-Z0-9._/-]*$/;
    if ((normalizedSeries && !reference.test(normalizedSeries)) || !reference.test(normalizedNumber)) {
      setError('Seria și numărul permit litere A-Z, cifre, punct, cratimă, / și _, fără spații interne.'); return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(invoiceDate) || !/^\d{4}-\d{2}-\d{2}$/.test(dueDate)) { setError('Completează data facturii și scadența.'); return; }
    if (dueDate < invoiceDate) { setError('Scadența nu poate fi înaintea datei facturii.'); return; }
    if (!lines.length || lines.length > 100) { setError('Adaugă între 1 și 100 de produse.'); return; }
    const items = [];
    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const quantity = decimal(line.quantity, 3, 15, true);
      const price = decimal(line.unit_price, 4, 14);
      const vat = decimal(line.vat_rate, 2, 3);
      if (!choices.products.some((product) => String(product.id) === line.product_id)) { setError(`Poziția ${index + 1}: selectează un produs activ.`); return; }
      if (quantity === null) { setError(`Poziția ${index + 1}: cantitate pozitivă, cu maximum 3 zecimale.`); return; }
      if (price === null) { setError(`Poziția ${index + 1}: preț nenegativ, cu maximum 4 zecimale.`); return; }
      if (vat === null || Number(vat) > 100) { setError(`Poziția ${index + 1}: TVA între 0 și 100, cu maximum 2 zecimale.`); return; }
      items.push({ product_id: Number(line.product_id), quantity, unit_price: price, vat_rate: vat,
        ...(editing && line.id ? { id: line.id } : {}),
        ...(line.purchase_order_item_id ? { purchase_order_item_id: line.purchase_order_item_id } : {}) });
    }
    let totals;
    try { totals = readTotals(declaredTotals); } catch (failure) { setError(failure.message); return; }
    submitting.current = true; setSaving(true); onBusyChange(true);
    try {
      const result = await api(editing ? `/invoices/${initialInvoice.id}` : '/invoices', { method: editing ? 'PATCH' : 'POST', body: {
        supplier_id: Number(supplierId), series: normalizedSeries, number: normalizedNumber,
        invoice_date: invoiceDate, due_date: dueDate, currency, items, declared_totals: totals,
        ...(editing ? { version: initialInvoice.version, reason: reason.trim() } : {}),
      } });
      onCreated(result.invoice);
    } catch (failure) {
      if ([401, 422].includes(failure.status)) onExpired();
      else if (failure.status === 0 || failure.status >= 500) {
        setUncertain(true); setError('Salvarea nu a putut fi confirmată. Verifică lista facturilor înainte să încerci din nou.');
      } else setError(failure.message);
    } finally { submitting.current = false; setSaving(false); onBusyChange(false); }
  }

  if (choices.loading) return <section className="panel feedback" role="status"><LoaderCircle className="spin" size={22} />Se încarcă…</section>;
  if (choices.error) return <section className="panel catalog-error"><p role="alert">{choices.error}</p><button className="button button-secondary" onClick={() => setAttempt((value) => value + 1)}>Încearcă din nou</button><button className="text-button" onClick={onCancel}>Înapoi la facturi</button></section>;
  const noCatalog = !choices.suppliers.length || !choices.products.length;
  const needsOrder = mode === 'order' && (source?.id !== orderId || !source?.order);
  return <form className="order-form invoice-form" onSubmit={submit}>
    {noCatalog && <div className="notice" role="status">Achizițiile trebuie să adauge {choices.suppliers.length ? 'un produs activ' : 'un furnizor activ'} în catalog.</div>}
    {error && <div className="error-message" role="alert" ref={errorBox} tabIndex={-1}><CircleAlert size={18} />{error}</div>}
    <fieldset className="order-fields" disabled={saving || uncertain || noCatalog}>
      {!editing && <section className="panel order-header invoice-source"><h2>Sursa facturii</h2><div className="invoice-header-grid">
        <div className="form-field"><label htmlFor="invoice-mode">Pornire factură</label><select id="invoice-mode" value={mode} onChange={(event) => changeMode(event.target.value)}><option value="order">Din comandă</option><option value="manual">Introducere manuală</option></select></div>
        {mode === 'order' && <div className="form-field"><label htmlFor="invoice-order">Comandă</label><select id="invoice-order" required value={orderId} onChange={(event) => setOrderId(event.target.value)}><option value="">Selectează comanda</option>{choices.orders.map((order) => <option key={order.id} value={order.id}>{order.number}</option>)}</select></div>}
      </div>{mode === 'order' && !choices.orders.length && <div className="notice" role="status">Nu există comenzi confirmate. Poți folosi introducerea manuală.</div>}
      {mode === 'order' && orderId && (source?.error ? <div className="catalog-error"><p role="alert">{source.error}</p><button type="button" className="button button-secondary" onClick={() => setSourceAttempt((value) => value + 1)}>Reîncarcă comanda</button></div> : needsOrder ? <p className="order-empty" role="status">Se încarcă pozițiile…</p> : null)}
      </section>}
      <section className="panel order-header"><h2>Detalii factură</h2><div className="invoice-header-grid">
        <div className="form-field"><label htmlFor="invoice-supplier">Furnizor</label><select id="invoice-supplier" required disabled={mode === 'order'} value={supplierId} onChange={(event) => setSupplierId(event.target.value)}><option value="">Selectează furnizorul</option>{choices.suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}</select></div>
        <div className="form-field"><label htmlFor="invoice-series">Serie (opțional)</label><input id="invoice-series" maxLength={40} value={series} onChange={(event) => setSeries(event.target.value)} /></div>
        <div className="form-field"><label htmlFor="invoice-number">Număr factură</label><input id="invoice-number" required maxLength={80} value={number} onChange={(event) => setNumber(event.target.value)} /></div>
        <div className="form-field"><label htmlFor="invoice-date">Data facturii</label><input id="invoice-date" type="date" required value={invoiceDate} onChange={(event) => setInvoiceDate(event.target.value)} /></div>
        <div className="form-field"><label htmlFor="invoice-due">Scadență</label><input id="invoice-due" type="date" required value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></div>
        <div className="form-field"><label htmlFor="invoice-currency">Monedă</label><select id="invoice-currency" value={currency} onChange={(event) => setCurrency(event.target.value)}><option>RON</option><option>EUR</option></select></div>
      </div></section>
      {editing && <div className="form-field invoice-edit-reason"><label htmlFor="invoice-edit-reason">Motivul corectării</label><input id="invoice-edit-reason" required maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /></div>}
      <section className="panel order-lines"><div className="panel-heading"><h2>Produse <span className="line-count">{lines.length}</span></h2><button type="button" className="button button-secondary" disabled={lines.length >= 100} onClick={() => setLines((current) => [...current, newLine()])}><Plus size={16} />Adaugă produs</button></div>
        {!lines.length && <p className="order-empty">Niciun produs adăugat.</p>}
        {lines.map((line, index) => <div className="order-line" key={line.key}><div className="order-line-heading"><strong>Poziția {index + 1}</strong><button type="button" className="icon-button" aria-label={`Elimină produsul ${index + 1}`} onClick={() => setLines((current) => current.filter((item) => item.key !== line.key))}><Trash2 size={16} /></button></div><div className="invoice-line-grid">
          <div className="form-field"><label htmlFor={`${line.key}-product`}>Produs {index + 1}</label><select id={`${line.key}-product`} required value={line.product_id} onChange={(event) => changeLine(line.key, 'product_id', event.target.value)}><option value="">Selectează produsul</option>{choices.products.map((product) => <option key={product.id} value={product.id}>{product.sku} · {product.name} ({product.unit})</option>)}</select></div>
          {[['quantity', 'Cantitate', 19], ['unit_price', 'Preț unitar', 19], ['vat_rate', 'TVA (%)', 6]].map(([field, label, limit]) => <div className="form-field" key={field}><label htmlFor={`${line.key}-${field}`}>{label} {index + 1}</label><input id={`${line.key}-${field}`} required inputMode="decimal" maxLength={limit} value={line[field]} onChange={(event) => changeLine(line.key, field, event.target.value)} /></div>)}
        </div>{line.source && <p className="invoice-source-quantities">Comandat: {line.source.quantity.replace('.', ',')} {line.source.unit} · Acceptat: {line.source.accepted_quantity.replace('.', ',')} · Asociat facturilor: {line.source.allocated_quantity.replace('.', ',')} · Disponibil de asociat: {line.source.available_quantity.replace('.', ',')}</p>}</div>)}
      </section>
      <DeclaredTotals values={declaredTotals} onChange={setDeclaredTotals} currency={currency} />
    </fieldset>
    <div className="order-form-footer"><button type="button" className="button button-secondary" disabled={saving} onClick={onCancel}><ArrowLeft size={16} />{uncertain ? 'Vezi facturile' : 'Anulează'}</button><button type="submit" className="button button-primary" disabled={saving || uncertain || noCatalog || needsOrder || !lines.length}>{saving ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />}{saving ? 'Se salvează…' : editing ? 'Salvează modificările' : 'Salvează ciorna'}</button></div>
  </form>;
}
