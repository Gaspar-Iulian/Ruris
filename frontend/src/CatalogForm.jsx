import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, CircleAlert, LoaderCircle, Save } from 'lucide-react';
import { api } from './api.js';

const units = [['BUC', 'Bucată'], ['KG', 'Kilogram'], ['L', 'Litru'], ['M', 'Metru'], ['M2', 'Metru pătrat'], ['M3', 'Metru cub']];

export default function CatalogForm({ kind, onCreated, onCancel, onExpired }) {
  const supplier = kind === 'supplier';
  const [name, setName] = useState('');
  const [sku, setSku] = useState('');
  const [unit, setUnit] = useState('BUC');
  const [country, setCountry] = useState('RO');
  const [taxId, setTaxId] = useState('');
  const [email, setEmail] = useState('');
  const [saving, setSaving] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState('');
  const submitting = useRef(false);
  const errorBox = useRef(null);
  useEffect(() => { if (error) errorBox.current?.focus(); }, [error]);

  async function submit(event) {
    event.preventDefault();
    if (submitting.current || uncertain) return;
    setError('');
    if (!name.trim()) { setError('Completează denumirea.'); return; }
    let body;
    if (supplier) {
      if (!/^[A-Z]{2}$/.test(country.trim().toUpperCase())) { setError('Țara trebuie să aibă două litere, de exemplu RO.'); return; }
      if (!taxId.trim()) { setError('Completează codul fiscal.'); return; }
      body = { name: name.trim(), tax_country: country.trim().toUpperCase(), tax_id: taxId.trim(), email: email.trim() || null };
    } else {
      const code = sku.trim().toUpperCase();
      if (!/^[A-Z0-9][A-Z0-9._-]{0,63}$/.test(code)) { setError('Codul permite litere, cifre, punct, cratimă și underscore, fără spații.'); return; }
      body = { name: name.trim(), sku: code, unit };
    }
    submitting.current = true;
    setSaving(true);
    try {
      const result = await api(supplier ? '/suppliers' : '/products', { method: 'POST', body });
      onCreated(result[supplier ? 'supplier' : 'product']);
    } catch (failure) {
      if ([401, 422].includes(failure.status)) onExpired();
      else if (failure.status === 0) {
        setUncertain(true);
        setError('Salvarea nu a putut fi confirmată. Verifică lista înainte să încerci din nou.');
      } else setError(failure.message);
    } finally { submitting.current = false; setSaving(false); }
  }

  return <form className="user-form" onSubmit={submit}>
    {error && <div className="error-message" role="alert" tabIndex={-1} ref={errorBox}><CircleAlert size={18} />{error}</div>}
    <fieldset className="order-fields" disabled={saving || uncertain}><section className="panel user-form-panel"><h2>{supplier ? 'Date furnizor' : 'Date produs'}</h2><div className="user-form-grid">
      <div className="form-field"><label htmlFor="catalog-name">Denumire</label><input id="catalog-name" required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} /></div>
      {supplier ? <>
        <div className="form-field"><label htmlFor="catalog-email">Email (opțional)</label><input id="catalog-email" type="email" maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></div>
        <div className="form-field"><label htmlFor="catalog-country">Țară</label><input id="catalog-country" required maxLength={2} value={country} onChange={(event) => setCountry(event.target.value.toUpperCase())} /></div>
        <div className="form-field"><label htmlFor="catalog-tax-id">Cod fiscal</label><input id="catalog-tax-id" required maxLength={64} value={taxId} onChange={(event) => setTaxId(event.target.value)} /></div>
      </> : <>
        <div className="form-field"><label htmlFor="catalog-sku">Cod produs</label><input id="catalog-sku" required maxLength={64} value={sku} onChange={(event) => setSku(event.target.value)} /></div>
        <div className="form-field"><label htmlFor="catalog-unit">Unitate de măsură</label><select id="catalog-unit" value={unit} onChange={(event) => setUnit(event.target.value)}>{units.map(([value, label]) => <option key={value} value={value}>{label} ({value})</option>)}</select></div>
      </>}
    </div></section></fieldset>
    <div className="order-form-footer"><button type="button" className="button button-secondary" disabled={saving} onClick={onCancel}><ArrowLeft size={16} />{uncertain ? 'Vezi lista' : 'Anulează'}</button><button type="submit" className="button button-primary" disabled={saving || uncertain}>{saving ? <LoaderCircle size={17} className="spin" /> : <Save size={17} />}{saving ? 'Se salvează…' : 'Salvează'}</button></div>
  </form>;
}
