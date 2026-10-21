import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, CircleAlert, LoaderCircle, Plus, Save, Trash2 } from 'lucide-react';
import { api } from './api.js';

const newLine = () => ({ key: crypto.randomUUID(), product_id: '', quantity: '1', unit_price: '', vat_rate: '0', expected_date: '' });

async function catalog(path, key, signal) {
  const records = [];
  let page = 1;
  while (true) {
    const data = await api(`${path}?page=${page}&per_page=100`, { signal });
    records.push(...data[key]);
    if (records.length >= data.total || data[key].length === 0) break;
    page += 1;
  }
  return records.filter((record) => record.is_active);
}

function decimal(value, scale, digits, positive = false) {
  const normalized = value.trim().replace(',', '.');
  if (!new RegExp(`^[0-9]{1,${digits}}(?:\\.[0-9]{1,${scale}})?$`).test(normalized)) return null;
  if (positive && !/[1-9]/.test(normalized)) return null;
  return normalized;
}

export default function OrderForm({ onExpired, onCancel, onCreated }) {
  const [supplierId, setSupplierId] = useState('');
  const [currency, setCurrency] = useState('RON');
  const [lines, setLines] = useState(() => [newLine()]);
  const [choices, setChoices] = useState({ loading: true, suppliers: [], products: [] });
  const [attempt, setAttempt] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const submitting = useRef(false);
  const errorBox = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    setChoices({ loading: true, suppliers: [], products: [] });
    Promise.all([catalog('/suppliers', 'suppliers', controller.signal), catalog('/products', 'products', controller.signal)])
      .then(([suppliers, products]) => setChoices({ loading: false, suppliers, products }))
      .catch((failure) => {
        if (failure.name === 'AbortError') return;
        if ([401, 422].includes(failure.status)) onExpired();
        else setChoices({ loading: false, suppliers: [], products: [], error: failure.message });
      });
    return () => controller.abort();
  }, [attempt, onExpired]);

  useEffect(() => { if (error) errorBox.current?.focus(); }, [error]);

  function changeLine(key, field, value) {
    setLines((current) => current.map((line) => line.key === key ? { ...line, [field]: value } : line));
  }

  async function submit(event) {
    event.preventDefault();
    if (submitting.current || uncertain) return;
    setError('');
    if (!choices.suppliers.some((supplier) => String(supplier.id) === supplierId)) {
      setError('Selectează un furnizor activ.'); return;
    }
    if (!lines.length) { setError('Adaugă cel puțin un produs.'); return; }
    const items = [];
    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const amount = decimal(line.quantity, 3, 15, true);
      const price = decimal(line.unit_price, 4, 14);
      const vat = decimal(line.vat_rate, 2, 3);
      if (!choices.products.some((product) => String(product.id) === line.product_id)) {
        setError(`Poziția ${index + 1}: selectează un produs activ.`); return;
      }
      if (amount === null) { setError(`Poziția ${index + 1}: cantitate pozitivă, cu maximum 3 zecimale.`); return; }
      if (price === null) { setError(`Poziția ${index + 1}: preț nenegativ, cu maximum 4 zecimale.`); return; }
      if (vat === null || Number(vat) > 100) { setError(`Poziția ${index + 1}: TVA între 0 și 100, cu maximum 2 zecimale.`); return; }
      if (!/^\d{4}-\d{2}-\d{2}$/.test(line.expected_date)) { setError(`Poziția ${index + 1}: completează termenul.`); return; }
      items.push({ product_id: Number(line.product_id), quantity: amount, unit_price: price, vat_rate: vat, expected_date: line.expected_date });
    }
    submitting.current = true;
    setSaving(true);
    try {
      const result = await api('/purchase-orders', { method: 'POST', body: { supplier_id: Number(supplierId), currency, items } });
      onCreated(result.order);
    } catch (failure) {
      if ([401, 422].includes(failure.status)) onExpired();
      else if (failure.status === 0) {
        setUncertain(true);
        setError('Salvarea nu a putut fi confirmată. Verifică lista comenzilor înainte să încerci din nou.');
      } else setError(failure.message);
    } finally { submitting.current = false; setSaving(false); }
  }

  if (choices.loading) return <section className="panel feedback" role="status"><LoaderCircle className="spin" size={22} />Se încarcă…</section>;
  if (choices.error) return <section className="panel catalog-error"><p role="alert">{choices.error}</p><button className="button button-secondary" onClick={() => setAttempt(attempt + 1)}>Încearcă din nou</button><button className="text-button" onClick={onCancel}>Înapoi la comenzi</button></section>;
  const noCatalog = choices.suppliers.length === 0 || choices.products.length === 0;
  return <form onSubmit={submit} className="order-form">
    {noCatalog && <div className="notice" role="status">Adaugă întâi {choices.suppliers.length === 0 ? 'un furnizor activ' : 'un produs activ'} în catalog.</div>}
    {error && <div className="error-message" role="alert" ref={errorBox} tabIndex={-1}><CircleAlert size={18} />{error}</div>}
    <fieldset disabled={saving || uncertain} className="order-fields"><section className="panel order-header"><h2>Detalii comandă</h2><div className="order-header-grid"><div className="form-field"><label htmlFor="order-supplier">Furnizor</label><select id="order-supplier" required value={supplierId} onChange={(event) => setSupplierId(event.target.value)}><option value="">Selectează furnizorul</option>{choices.suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}</select></div><div className="form-field"><label htmlFor="order-currency">Monedă</label><select id="order-currency" value={currency} onChange={(event) => setCurrency(event.target.value)}><option>RON</option><option>EUR</option></select></div></div></section>
      <section className="panel order-lines"><div className="panel-heading"><h2>Produse <span className="line-count">{lines.length}</span></h2><button type="button" className="button button-secondary" disabled={lines.length >= 100 || noCatalog} onClick={() => setLines((current) => [...current, newLine()])}><Plus size={16} />Adaugă produs</button></div>
        {!lines.length && <p className="order-empty">Niciun produs adăugat.</p>}
        {lines.map((line, index) => <div className="order-line" key={line.key}><div className="order-line-heading"><strong>Poziția {index + 1}</strong><button type="button" className="icon-button" aria-label={`Elimină poziția ${index + 1}`} onClick={() => setLines((current) => current.filter((item) => item.key !== line.key))}><Trash2 size={16} /></button></div><div className="order-line-grid">
          <div className="form-field product-field"><label htmlFor={`${line.key}-product`}>Produs {index + 1}</label><select id={`${line.key}-product`} required value={line.product_id} onChange={(event) => changeLine(line.key, 'product_id', event.target.value)}><option value="">Selectează produsul</option>{choices.products.map((product) => <option key={product.id} value={product.id}>{product.sku} · {product.name} ({product.unit})</option>)}</select></div>
          {[['quantity', 'Cantitate', '1'], ['unit_price', 'Preț unitar', '0,00'], ['vat_rate', 'TVA (%)', '0']].map(([field, label, placeholder]) => <div className="form-field" key={field}><label htmlFor={`${line.key}-${field}`}>{label} {index + 1}</label><input id={`${line.key}-${field}`} type="text" inputMode="decimal" required maxLength={40} placeholder={placeholder} value={line[field]} onChange={(event) => changeLine(line.key, field, event.target.value)} /></div>)}
          <div className="form-field"><label htmlFor={`${line.key}-date`}>Termen {index + 1}</label><input id={`${line.key}-date`} type="date" required value={line.expected_date} onChange={(event) => changeLine(line.key, 'expected_date', event.target.value)} /></div>
        </div></div>)}
      </section></fieldset>
    <div className="order-form-footer"><button className="button button-secondary" type="button" disabled={saving} onClick={onCancel}><ArrowLeft size={16} />{uncertain ? 'Vezi comenzile' : 'Anulează'}</button><button className="button button-primary" type="submit" disabled={saving || uncertain || noCatalog || !lines.length}>{saving ? <LoaderCircle size={17} className="spin" /> : <Save size={17} />}{saving ? 'Se salvează…' : 'Salvează ciorna'}</button></div>
  </form>;
}
