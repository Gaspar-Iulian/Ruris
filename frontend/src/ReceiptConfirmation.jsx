import { useRef, useState } from 'react';
import { Check, CircleAlert, LoaderCircle, RefreshCw } from 'lucide-react';
import { api } from './api.js';
import { quantityText } from './receiptQuantities.js';
import ReceiptBalance from './ReceiptBalance.jsx';

function amount(value) {
  const normalized = value.trim().replace(',', '.');
  if (!/^[0-9]{1,15}(?:\.[0-9]{1,3})?$/.test(normalized)) return null;
  const [whole, fraction = ''] = normalized.split('.');
  return { text: normalized, thousandths: BigInt(whole) * 1000n + BigInt(fraction.padEnd(3, '0')) };
}

export default function ReceiptConfirmation({ receipt, onExpired, onConfirmed, onBusyChange, onReload }) {
  const [quantities, setQuantities] = useState(() => Object.fromEntries(receipt.items.map((line) => [line.id, {
    accepted_quantity: line.purchase_order_item_id ? quantityText(line.received_quantity, '.') : '0', rejected_quantity: '0',
    pending_quantity: line.purchase_order_item_id ? '0' : quantityText(line.received_quantity, '.'),
  }])));
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [requiresReload, setRequiresReload] = useState(false);
  const submitting = useRef(false);

  function change(id, field, value) {
    setQuantities((current) => ({ ...current, [id]: { ...current[id], [field]: value } }));
  }

  async function submit(event) {
    event.preventDefault();
    if (submitting.current || requiresReload) return;
    setError('');
    if (!reason.trim()) { setError('Completează observațiile confirmării.'); return; }
    const items = [];
    for (const line of receipt.items) {
      const parsed = Object.fromEntries(Object.entries(quantities[line.id]).map(([key, value]) => [key, amount(value)]));
      if (Object.values(parsed).some((value) => value === null)) {
        setError(`Poziția ${line.line_number}: cantități nenegative, cu maximum 3 zecimale.`); return;
      }
      if (Object.values(parsed).reduce((sum, value) => sum + value.thousandths, 0n) !== amount(line.received_quantity).thousandths) {
        setError(`Poziția ${line.line_number}: acceptat + respins + în așteptare trebuie să fie egal cu ${quantityText(line.received_quantity)} ${line.unit}.`); return;
      }
      items.push({ id: line.id, ...Object.fromEntries(Object.entries(parsed).map(([key, value]) => [key, value.text])) });
    }
    if (!items.length) { setError('Recepția nu are poziții de confirmat.'); return; }
    submitting.current = true; setSaving(true); onBusyChange(true);
    try {
      const result = await api(`/receipts/${receipt.id}/confirm`, { method: 'POST', body: {
        version: receipt.version, reason: reason.trim(), items,
      } });
      onConfirmed(result.receipt);
    } catch (failure) {
      if ([401, 422].includes(failure.status)) onExpired();
      else if (failure.status === 0 || failure.status >= 500) {
        setError('Confirmarea nu a putut fi verificată. Actualizează datele înainte să încerci din nou.'); setRequiresReload(true);
      } else { setError(failure.message); setRequiresReload(failure.status === 409); }
    } finally { submitting.current = false; setSaving(false); onBusyChange(false); }
  }

  return <form className="receipt-confirmation" onSubmit={submit}>
    <h3>Confirmare recepție</h3><p className="field-hint">Se adaugă în stoc doar cantitatea acceptată.</p>
    {error && <div className="error-message" role="alert"><CircleAlert size={18} />{error}</div>}
    <fieldset className="order-fields" disabled={saving || requiresReload}>
      {receipt.items.map((line) => <section className="receipt-classification" key={line.id} aria-label={`Clasificare poziția ${line.line_number}`}>
        <h4>{line.line_number}. {line.description}</h4><p className="field-hint">Sosit: {quantityText(line.received_quantity)} {line.unit}</p>
        {!line.purchase_order_item_id && <p className="field-hint">Fără comandă: marfa rămâne în așteptare până la clarificare sau poate fi respinsă.</p>}
        <div className="classification-grid">{[['accepted_quantity', 'Acceptat'], ['rejected_quantity', 'Respins'], ['pending_quantity', 'În așteptare']].map(([field, label]) => <div className="form-field" key={field}><label htmlFor={`classify-${line.id}-${field}`}>{label} {line.line_number}</label><input id={`classify-${line.id}-${field}`} required inputMode="decimal" maxLength={19} disabled={field === 'accepted_quantity' && !line.purchase_order_item_id} value={quantities[line.id][field]} onChange={(event) => change(line.id, field, event.target.value)} /></div>)}</div>
      <ReceiptBalance received={line.received_quantity} values={quantities[line.id]} unit={line.unit} />
      </section>)}
      <div className="form-field"><label htmlFor="receipt-confirm-reason">Observații</label><input id="receipt-confirm-reason" required maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /></div>
    </fieldset>
    <div className="document-actions">{requiresReload && <button type="button" className="button button-secondary" onClick={onReload}><RefreshCw size={16} />Actualizează datele</button>}<button className="button button-primary" type="submit" disabled={saving || requiresReload || !receipt.items.length}>{saving ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}{saving ? 'Se confirmă…' : 'Confirmă recepția'}</button></div>
  </form>;
}
