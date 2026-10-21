import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, CircleAlert, Eye, EyeOff, LoaderCircle, UserPlus } from 'lucide-react';
import { api } from './api.js';

export default function UserForm({ onCancel, onCreated, onExpired }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [visible, setVisible] = useState(false);
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
    if (!name.trim()) { setError('Completează numele.'); return; }
    if (!['ACHIZITII', 'DEPOZIT', 'CONTABILITATE'].includes(role)) { setError('Selectează rolul.'); return; }
    if (Array.from(password).length < 12) { setError('Parola trebuie să aibă minimum 12 caractere.'); return; }
    if (new TextEncoder().encode(password).length > 72) { setError('Parola este prea lungă. Folosește maximum 72 de octeți UTF-8.'); return; }
    if (password !== confirmation) { setError('Parolele nu coincid.'); return; }
    submitting.current = true;
    setSaving(true);
    try {
      const result = await api('/users', { method: 'POST', body: { name: name.trim(), email: email.trim(), password, role } });
      setPassword(''); setConfirmation('');
      onCreated(result.user);
    } catch (failure) {
      if ([401, 422].includes(failure.status)) onExpired();
      else if (failure.status === 0) {
        setUncertain(true);
        setPassword(''); setConfirmation('');
        setError('Crearea contului nu a putut fi confirmată. Verifică lista utilizatorilor.');
      } else setError(failure.message);
    } finally { submitting.current = false; setSaving(false); }
  }

  return <form className="user-form" onSubmit={submit}>
    {error && <div className="error-message" ref={errorBox} tabIndex={-1} role="alert"><CircleAlert size={18} />{error}</div>}
    <fieldset className="order-fields" disabled={saving || uncertain}><section className="panel user-form-panel"><h2>Date utilizator</h2><div className="user-form-grid">
      <div className="form-field"><label htmlFor="new-user-name">Nume</label><input id="new-user-name" required maxLength={120} autoComplete="off" value={name} onChange={(event) => setName(event.target.value)} /></div>
      <div className="form-field"><label htmlFor="new-user-email">Email</label><input id="new-user-email" type="email" required maxLength={254} autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} /></div>
      <div className="form-field user-role-field"><label htmlFor="new-user-role">Rol</label><select id="new-user-role" required value={role} onChange={(event) => setRole(event.target.value)}><option value="">Selectează rolul</option><option value="ACHIZITII">Achiziții</option><option value="DEPOZIT">Depozit</option><option value="CONTABILITATE">Contabilitate</option></select></div>
      <div className="form-field"><label htmlFor="new-user-password">Parolă</label><div className="password-field"><input id="new-user-password" type={visible ? 'text' : 'password'} required autoComplete="new-password" aria-describedby="new-user-password-hint" value={password} onChange={(event) => setPassword(event.target.value)} /><button type="button" className="icon-button" aria-label={visible ? 'Ascunde parola' : 'Arată parola'} aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div><small id="new-user-password-hint" className="field-hint">Minimum 12 caractere.</small></div>
      <div className="form-field"><label htmlFor="new-user-confirmation">Confirmă parola</label><input id="new-user-confirmation" type={visible ? 'text' : 'password'} required autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></div>
    </div></section></fieldset>
    <div className="order-form-footer"><button type="button" className="button button-secondary" disabled={saving} onClick={onCancel}><ArrowLeft size={16} />{uncertain ? 'Vezi utilizatorii' : 'Anulează'}</button><button className="button button-primary" type="submit" disabled={saving || uncertain}>{saving ? <LoaderCircle size={17} className="spin" /> : <UserPlus size={17} />}{saving ? 'Se creează…' : 'Creează contul'}</button></div>
  </form>;
}
