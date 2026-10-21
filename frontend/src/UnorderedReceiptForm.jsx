import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, CircleAlert, LoaderCircle, Plus, Save, Trash2 } from 'lucide-react';
import { api } from './api.js';
import { parseQuantity } from './receiptQuantities.js';

const units = ['BUC', 'KG', 'L', 'M', 'M2', 'M3'];
const blankLine = (key) => ({ key, product_id: '', description: '', unit: 'BUC', received_quantity: '' });

async function catalog(path, key, signal) {
  const records = [];
  for (let page = 1; ; page += 1) {
    const data = await api(`${path}?page=${page}&per_page=100`, { signal });
    records.push(...data[key]);
    if (!data[key].length || records.length >= data.total) return records.filter((record) => record.is_active);
  }
}

export default function UnorderedReceiptForm({ onExpired, onCancel, onCreated, onBusyChange }) {
  const [choices, setChoices] = useState({ loading: true });
  const [attempt, setAttempt] = useState(0);
  const [supplierId, setSupplierId] = useState('');
  const [reference, setReference] = useState('');
  const [receivedAt, setReceivedAt] = useState(() => {
    const date = new Date();
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  });
  const [lines, setLines] = useState([blankLine(1)]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const nextKey = useRef(2);
  const submitting = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    setChoices({ loading: true });
    Promise.all([catalog('/suppliers', 'suppliers', controller.signal), catalog('/products', 'products', controller.signal)])
      .then(([suppliers, products]) => { if (!controller.signal.aborted) setChoices({ suppliers, products }); })
      .catch((failure) => {
        if (failure.name === 'AbortError' || controller.signal.aborted) return;
        if ([401, 422].includes(failure.status)) onExpired();
        else setChoices({ error: failure.message });
      });
    return () => controller.abort();
  }, [attempt, onExpired]);

  function change(key, field, value) {
    setLines((current) => current.map((line) => {
      if (line.key !== key) return line;
      if (field !== 'product_id') return { ...line, [field]: value };
      const product = choices.products.find((item) => String(item.id) === value);
      return { ...line, product_id: value, description: product?.name || '', unit: product?.unit || 'BUC' };
    }));
  }

  async function submit(event) {
    event.preventDefault();
    if (submitting.current || uncertain) return;
    setError('');
    if (!choices.suppliers.some((item) => String(item.id) === supplierId)) { setError('Selectează un furnizor activ.'); return; }
    const items = [];
    for (const [index, line] of lines.entries()) {
      const amount = parseQuantity(line.received_quantity);
      if (!line.description.trim() || !amount || amount.thousandths === 0n) {
        setError(`Poziția ${index + 1}: completează descrierea și o cantitate pozitivă, cu maximum 3 zecimale.`); return;
      }
      items.push({ product_id: line.product_id ? Number(line.product_id) : null, description: line.description.trim(),
        unit: line.unit, received_quantity: amount.text });
    }
    const moment = new Date(receivedAt);
    if (!reference.trim() || Number.isNaN(moment.getTime())) { setError('Completează documentul de livrare și momentul sosirii.'); return; }
    submitting.current = true; setSaving(true); onBusyChange(true);
    let keepModeLocked = false;
    try {
      const result = await api('/receipts/unordered', { method: 'POST', body: { supplier_id: Number(supplierId),
        delivery_reference: reference.trim(), received_at: moment.toISOString(), items } });
      onCreated(result.receipt);
    } catch (failure) {
      if ([401, 422].includes(failure.status)) onExpired();
      else if (failure.status === 0 || failure.status >= 500) {
        keepModeLocked = true;
        setUncertain(true); setError('Salvarea nu a putut fi confirmată. Verifică recepțiile înainte de o nouă încercare.');
      } else setError(failure.message);
    } finally { submitting.current = false; setSaving(false); onBusyChange(keepModeLocked); }
  }

  if (choices.loading) return <section className="panel feedback" role="status"><LoaderCircle className="spin" />Se încarcă…</section>;
  if (choices.error) return <section className="panel catalog-error"><p role="alert">{choices.error}</p><button className="button button-secondary" onClick={() => setAttempt((value) => value + 1)}>Încearcă din nou</button></section>;
  return <form className="order-form" onSubmit={submit}>
    {error && <div className="error-message" role="alert"><CircleAlert size={18} />{error}</div>}
    {!choices.suppliers.length && <div className="notice">Achizițiile trebuie să adauge mai întâi furnizorul în catalog.</div>}
    <fieldset className="order-fields" disabled={saving || uncertain || !choices.suppliers.length}>
      <section className="panel order-header"><h2>Sosire fără comandă</h2><div className="user-form-grid receipt-header-grid">
        <div className="form-field"><label htmlFor="unordered-supplier">Furnizor</label><select id="unordered-supplier" required value={supplierId} onChange={(event) => setSupplierId(event.target.value)}><option value="">Selectează furnizorul</option>{choices.suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}</select></div>
        <div className="form-field"><label htmlFor="unordered-reference">Document de livrare</label><input id="unordered-reference" required maxLength={120} value={reference} onChange={(event) => setReference(event.target.value)} /></div>
        <div className="form-field"><label htmlFor="unordered-date">Data și ora recepției</label><input id="unordered-date" type="datetime-local" required value={receivedAt} onChange={(event) => setReceivedAt(event.target.value)} /></div>
      </div><p className="field-hint">După confirmare, marfa rămâne în așteptare. Stocul crește doar la acceptare.</p></section>
      <section className="panel order-lines"><h2>Produse sosite</h2>{lines.map((line, index) => <section className="unordered-line" key={line.key} aria-label={`Produs sosit ${index + 1}`}>
        <div className="pending-grid">
          <div className="form-field"><label htmlFor={`unordered-product-${line.key}`}>Produs {index + 1}</label><select id={`unordered-product-${line.key}`} value={line.product_id} onChange={(event) => change(line.key, 'product_id', event.target.value)}><option value="">Produs neidentificat</option>{choices.products.map((product) => <option key={product.id} value={product.id}>{product.sku} · {product.name}</option>)}</select></div>
          <div className="form-field"><label htmlFor={`unordered-description-${line.key}`}>Descriere {index + 1}</label><input id={`unordered-description-${line.key}`} required maxLength={200} readOnly={Boolean(line.product_id)} value={line.description} onChange={(event) => change(line.key, 'description', event.target.value)} /></div>
          <div className="form-field"><label htmlFor={`unordered-unit-${line.key}`}>Unitate {index + 1}</label><select id={`unordered-unit-${line.key}`} disabled={Boolean(line.product_id)} value={line.unit} onChange={(event) => change(line.key, 'unit', event.target.value)}>{units.map((unit) => <option key={unit}>{unit}</option>)}</select></div>
          <div className="form-field"><label htmlFor={`unordered-quantity-${line.key}`}>Cantitate sosită {index + 1}</label><input id={`unordered-quantity-${line.key}`} required inputMode="decimal" maxLength={19} value={line.received_quantity} onChange={(event) => change(line.key, 'received_quantity', event.target.value)} /></div>
        </div>{lines.length > 1 && <button type="button" className="text-button" aria-label={`Elimină produsul sosit ${index + 1}`} onClick={() => setLines((current) => current.filter((item) => item.key !== line.key))}><Trash2 size={16} />Elimină</button>}
      </section>)}<button type="button" className="button button-secondary" disabled={lines.length >= 100} onClick={() => setLines((current) => [...current, blankLine(nextKey.current++)])}><Plus size={16} />Adaugă produs</button></section>
    </fieldset>
    <div className="order-form-footer"><button type="button" className="button button-secondary" disabled={saving} onClick={onCancel}><ArrowLeft size={16} />{uncertain ? 'Vezi recepțiile' : 'Anulează'}</button><button type="submit" className="button button-primary" disabled={saving || uncertain || !choices.suppliers.length}>{saving ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />}Salvează ciorna</button></div>
  </form>;
}
