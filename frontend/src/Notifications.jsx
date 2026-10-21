import { useEffect, useState } from 'react';
import { Bell, LoaderCircle } from 'lucide-react';
import { api } from './api.js';

const statuses = { PENDING: 'În așteptare', SENDING: 'În curs', SENT: 'Acceptat de server', FAILED: 'Eșuat', UNKNOWN: 'De verificat', SKIPPED: 'Nu mai este actual' };
const kinds = { OVERDUE: 'Comenzi întârziate', BLOCKED_INVOICES: 'Facturi blocate', RECEIPT_BUYER: 'Clarificări recepții', RECEIPT_WAREHOUSE: 'Marfă de verificat' };
const errors = { SMTP_NOT_ACCEPTED: 'Mesaj neacceptat de server', SMTP_RESULT_UNKNOWN: 'Rezultatul trimiterii este neclar',
  RECIPIENT_OR_DIGEST_CHANGED: 'Destinatarul sau situația documentelor s-a schimbat', WORKER_INTERRUPTED: 'Procesarea a fost întreruptă; trimiterea trebuie verificată' };
const dateTime = (value) => value ? new Intl.DateTimeFormat('ro-RO', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value)) : '—';

export default function Notifications({ onExpired, refresh }) {
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true });
    api(`/notifications?page=${page}&per_page=20`, { signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted) setState({ data });
    }).catch((failure) => {
      if (controller.signal.aborted || failure.name === 'AbortError') return;
      if ([401, 422].includes(failure.status)) onExpired();
      else setState({ error: failure.message });
    });
    return () => controller.abort();
  }, [page, attempt, refresh, onExpired]);
  return <section className="panel notifications-panel" aria-label="Jurnal notificări"><div className="panel-heading"><div><h2>Notificările mele</h2><p>{state.data?.total ?? '…'} mesaje</p></div></div>
    {state.loading ? <div className="feedback" role="status"><LoaderCircle className="spin" />Se încarcă…</div> : state.error ? <div className="catalog-error"><p role="alert">{state.error}</p><button className="button button-secondary" onClick={() => setAttempt((value) => value + 1)}>Încearcă din nou</button></div> : <>
      {!state.data.notifications?.length ? <div className="feedback"><Bell size={24} />Nu există notificări de afișat.</div> : <div className="notification-list">{state.data.notifications.map((message) => <details className="notification-entry" key={message.id}><summary><div><strong>{message.subject}</strong><p>{kinds[message.kind]} · {message.as_of} · {message.transport === 'LOCAL_MAILPIT' ? 'Test local' : 'SMTP'}</p></div><span className={`status notification-${message.status.toLowerCase()}`}>{statuses[message.status] || message.status}</span></summary>
        <div className="notification-content"><pre>{message.body}</pre><p>Încercări: {message.attempt_count} · Creat: {dateTime(message.created_at)}{message.sent_at ? ` · Acceptat: ${dateTime(message.sent_at)}` : ''}</p>
          {message.next_attempt_at && <p>Următoarea încercare: {dateTime(message.next_attempt_at)}</p>}
          {message.last_error && <p>{errors[message.last_error] || 'Consultă starea mesajului.'}</p>}
          {message.attempts?.length > 0 && <ul>{message.attempts.map((item) => <li key={item.number}>Încercarea {item.number}: {statuses[item.status]} · {dateTime(item.started_at)}</li>)}</ul>}
        </div>
      </details>)}</div>}
      {state.data.total > 20 && <div className="pagination"><span>Pagina {page} din {Math.ceil(state.data.total / 20)}</span><div><button type="button" className="button button-secondary" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Anterior</button><button type="button" className="button button-secondary" disabled={page * 20 >= state.data.total} onClick={() => setPage((value) => value + 1)}>Următor</button></div></div>}
    </>}
  </section>;
}
