import { useEffect, useRef, useState } from 'react';
import { ChevronDown, CircleAlert, Download, LoaderCircle, Paperclip, Upload } from 'lucide-react';
import { api, apiFile } from './api.js';

const MAX_BYTES = 10 * 1024 * 1024;
const sizes = (value) => value < 1024 * 1024 ? `${Math.ceil(value / 1024)} KB` : `${(value / (1024 * 1024)).toLocaleString('ro-RO', { maximumFractionDigits: 1 })} MB`;
const moment = (value) => new Intl.DateTimeFormat('ro-RO', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));

export default function DocumentAttachments(props) {
  const [open, setOpen] = useState(false);
  return <section className="document-attachments" aria-label="Documente atașate">
    <button type="button" className="history-toggle" aria-expanded={open} onClick={() => setOpen((value) => !value)}><Paperclip size={17} />Documente<ChevronDown size={16} /></button>
    {open && <AttachmentList {...props} />}
  </section>;
}

function AttachmentList({ kind, document: parent, onExpired, onChanged, onBusyChange, onReload }) {
  const [state, setState] = useState({ loading: true });
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [file, setFile] = useState(null);
  const [reason, setReason] = useState('');
  const [uploadKey, setUploadKey] = useState(() => crypto.randomUUID());
  const [withdrawal, setWithdrawal] = useState(null);
  const [withdrawalReason, setWithdrawalReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [requiresReload, setRequiresReload] = useState(false);
  const submitting = useRef(false);
  const input = useRef(null);
  const errorBox = useRef(null);
  const endpoint = `/documents/${kind}/${parent.id}/attachments`;

  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true });
    api(`${endpoint}?page=${page}&per_page=10`, { signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted) setState({ data });
    }).catch((failure) => {
      if (failure.name === 'AbortError' || controller.signal.aborted) return;
      if ([401, 422].includes(failure.status)) onExpired();
      else setState({ error: failure.message });
    });
    return () => controller.abort();
  }, [endpoint, parent.version, page, revision, onExpired]);
  useEffect(() => { if (error) errorBox.current?.focus(); }, [error]);

  function working(value) {
    submitting.current = value; setBusy(value); onBusyChange(value);
  }

  function failed(failure, mutation = false) {
    if ([401, 422].includes(failure.status)) { onExpired(); return; }
    if (mutation && (failure.status === 0 || failure.status >= 500)) {
      setError('Rezultatul nu a putut fi confirmat. Actualizează documentul și verifică lista fișierelor înainte de o nouă operație.');
      setRequiresReload(true);
    } else {
      setError(failure.message);
      if (mutation && failure.status === 409) setRequiresReload(true);
    }
  }

  function selectFile(event) {
    const selected = event.target.files[0] || null;
    setFile(selected); setUploadKey(crypto.randomUUID()); setError('');
  }

  async function upload(event) {
    event.preventDefault();
    if (submitting.current || requiresReload) return;
    if (!file) { setError('Selectează un fișier.'); return; }
    if (!/\.(pdf|png|jpe?g)$/i.test(file.name)) { setError('Selectează un fișier PDF, PNG sau JPG.'); return; }
    if (file.size === 0 || file.size > MAX_BYTES) { setError('Fișierul trebuie să aibă între 1 octet și 10 MB.'); return; }
    if (!reason.trim()) { setError('Completează observațiile fișierului.'); return; }
    const body = new FormData();
    body.append('file', file); body.append('version', String(parent.version));
    body.append('reason', reason.trim()); body.append('upload_key', uploadKey);
    working(true); setError('');
    try {
      const result = await api(endpoint, { method: 'POST', body });
      setFile(null); setReason(''); setUploadKey(crypto.randomUUID()); setPage(1);
      if (input.current) input.current.value = '';
      onChanged(result.document, result.document.status === 'DRAFT' && kind === 'invoices' ? 'Fișier atașat. Verifică din nou factura înainte de aprobare.' : 'Fișierul a fost atașat.');
      setRevision((value) => value + 1);
    } catch (failure) { failed(failure, true); }
    finally { working(false); }
  }

  async function withdraw(event) {
    event.preventDefault();
    if (submitting.current || requiresReload || !withdrawal) return;
    if (!withdrawalReason.trim()) { setError('Completează motivul retragerii.'); return; }
    working(true); setError('');
    try {
      const result = await api(`/attachments/${withdrawal.id}/withdraw`, { method: 'POST', body: { version: parent.version, reason: withdrawalReason.trim() } });
      setWithdrawal(null); setWithdrawalReason(''); onChanged(result.document, 'Fișierul a fost retras. Istoricul este păstrat.');
      setRevision((value) => value + 1);
    } catch (failure) { failed(failure, true); }
    finally { working(false); }
  }

  async function download(record) {
    if (submitting.current) return;
    working(true); setError('');
    let url;
    try {
      const blob = await apiFile(`/attachments/${record.id}/download`);
      url = URL.createObjectURL(blob);
      const link = window.document.createElement('a');
      link.href = url; link.download = record.original_name; window.document.body.append(link); link.click(); link.remove();
    } catch (failure) { failed(failure); }
    finally {
      if (url) setTimeout(() => URL.revokeObjectURL(url), 1000);
      working(false);
    }
  }

  if (state.loading) return <p className="field-hint" role="status"><LoaderCircle className="spin" size={16} /> Se încarcă documentele…</p>;
  if (state.error) return <div className="catalog-error"><p role="alert">{state.error}</p><button className="button button-secondary" onClick={() => setRevision((value) => value + 1)}>Reîncarcă fișierele</button></div>;
  const data = state.data;
  const stale = requiresReload || data.document_version !== parent.version;
  const canManage = data.can_manage && !stale;
  const atLimit = data.total >= data.max_attachments;

  return <div className="attachment-content">
    {error && <div className="error-message" role="alert" ref={errorBox} tabIndex={-1}><CircleAlert size={17} />{error}</div>}
    {stale && <div className="notice"><p>Actualizează documentul înainte de o nouă modificare.</p><button type="button" className="button button-secondary" onClick={onReload}>Actualizează documentul</button></div>}
    {!data.attachments?.length ? <p className="field-hint">Niciun fișier atașat.</p> : <ul className="attachment-list">{data.attachments.map((record) => <li key={record.id}>
      <div className="attachment-description"><strong>{record.original_name}</strong><span className={`status ${record.status === 'WITHDRAWN' ? 'attachment-withdrawn' : 'attachment-active'}`}>{record.status === 'WITHDRAWN' ? 'Retras' : 'Activ'}</span>
        <p>{sizes(record.size_bytes)} · {record.uploaded_by_name} · {moment(record.created_at)}</p><p>{record.upload_reason}</p>
        {record.status === 'WITHDRAWN' && <p className="attachment-withdrawal">Retras de {record.withdrawn_by_name} · {moment(record.withdrawn_at)} · {record.withdrawal_reason}</p>}
      </div>
      <div className="attachment-actions"><button type="button" className="button button-secondary" disabled={busy} aria-label={`Descarcă ${record.original_name}`} onClick={() => download(record)}><Download size={15} />Descarcă</button>
        {canManage && record.status === 'ACTIVE' && <button type="button" className="text-button" disabled={busy} aria-label={`Retrage ${record.original_name}`} onClick={() => { setWithdrawal(record); setWithdrawalReason(''); setError(''); }}>Retrage</button>}</div>
    </li>)}</ul>}
    {data.total > 10 && <div className="pagination"><span>Pagina {page} din {Math.ceil(data.total / 10)}</span><div><button type="button" className="button button-secondary" disabled={busy || page === 1} onClick={() => setPage((value) => value - 1)}>Mai recente</button><button type="button" className="button button-secondary" disabled={busy || page * 10 >= data.total} onClick={() => setPage((value) => value + 1)}>Mai vechi</button></div></div>}
    {withdrawal && canManage && <form className="attachment-form" onSubmit={withdraw}><h3>Retrage {withdrawal.original_name}</h3><div className="form-field"><label htmlFor="attachment-withdrawal-reason">Motivul retragerii</label><input id="attachment-withdrawal-reason" required maxLength={1000} value={withdrawalReason} onChange={(event) => setWithdrawalReason(event.target.value)} /></div>
      <div className="workflow-actions"><button className="button button-primary" type="submit" disabled={busy}>Confirmă retragerea</button><button className="button button-secondary" type="button" disabled={busy} onClick={() => setWithdrawal(null)}>Anulează retragerea</button></div></form>}
    {canManage && !atLimit && <form className="attachment-form" onSubmit={upload}><h3>Adaugă fișier</h3><p className="field-hint">PDF, PNG sau JPG · maximum 10 MB. Conținutul se verifică manual.</p>
      <div className="form-field"><label htmlFor="attachment-file">Fișier</label><input id="attachment-file" ref={input} type="file" accept=".pdf,.png,.jpg,.jpeg" required disabled={busy} onChange={selectFile} /></div>
      <div className="form-field"><label htmlFor="attachment-upload-reason">Observații fișier</label><input id="attachment-upload-reason" required maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /></div>
      <button className="button button-primary" type="submit" disabled={busy}><Upload size={16} />Încarcă fișierul</button></form>}
    {canManage && atLimit && <p className="notice">Documentul are deja {data.max_attachments} de fișiere în istoric.</p>}
    {!data.can_manage && <p className="field-hint">Documentele sunt disponibile pentru consultare.</p>}
    {busy && <p className="field-hint" role="status">Se procesează fișierul…</p>}
  </div>;
}
