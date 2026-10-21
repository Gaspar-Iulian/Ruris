import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowDownLeft, ArrowRight, Bell, Boxes, Check, ChevronLeft, ChevronRight, CircleAlert, ClipboardList, Eye, EyeOff, FileCheck2, LayoutDashboard, LoaderCircle, LogOut, Menu, Package, RefreshCw, Search, ShieldCheck, ShoppingCart, Truck, Users, X } from 'lucide-react';
import { api } from './api.js';
import OrderForm from './OrderForm.jsx';
import UserForm from './UserForm.jsx';
import CatalogForm from './CatalogForm.jsx';
import ReceiptForm from './ReceiptForm.jsx';
import InvoiceForm from './InvoiceForm.jsx';
import InvoiceWorkflow from './InvoiceWorkflow.jsx';
import ReceiptConfirmation from './ReceiptConfirmation.jsx';
import ReceiptPendingWorkflow from './ReceiptPendingWorkflow.jsx';
import DocumentHistory from './DocumentHistory.jsx';
import DocumentAttachments from './DocumentAttachments.jsx';
import Notifications from './Notifications.jsx';
import DocumentLinesTable from './DocumentLinesTable.jsx';
import { quantityText as quantity } from './receiptQuantities.js';
import AmountsPreview from './AmountsPreview.jsx';
import rurisLogo from './assets/ruris-logo.png';

const roles = { ADMIN: 'Administrare', ACHIZITII: 'Achiziții', DEPOZIT: 'Depozit', CONTABILITATE: 'Contabilitate' };
const states = { DRAFT: 'Ciornă', CONFIRMED: 'Confirmată', CLOSED: 'Închisă', CANCELLED: 'Anulată', BLOCKED: 'Blocată', VERIFIED: 'Verificată', APPROVED: 'Aprobată', PAID: 'Plătită' };
const views = {
  orders: { label: 'Comenzi', icon: ShoppingCart, endpoint: '/purchase-orders', key: 'orders', singular: 'Comandă' },
  receipts: { label: 'Recepții', icon: Truck, endpoint: '/receipts', key: 'receipts', singular: 'Recepție' },
  pending: { label: 'Clarificări', icon: CircleAlert, endpoint: '/receipts/pending', key: 'receipts', singular: 'Recepție' },
  notifications: { label: 'Notificări', icon: Bell, endpoint: '/notifications', key: 'notifications' },
  invoices: { label: 'Facturi', icon: FileCheck2, endpoint: '/invoices', key: 'invoices', singular: 'Factură' },
  stock: { label: 'Stoc', icon: Boxes, endpoint: '/stock', key: 'stock' },
  products: { label: 'Produse', icon: Package, endpoint: '/products', key: 'products' },
  suppliers: { label: 'Furnizori', icon: Truck, endpoint: '/suppliers', key: 'suppliers' },
  overdue: { label: 'Întârzieri', icon: CircleAlert, endpoint: '/purchase-orders/overdue', key: 'items' },
  users: { label: 'Utilizatori', icon: Users, endpoint: '/users', key: 'users' },
};
const primary = { ADMIN: 'users', ACHIZITII: 'orders', DEPOZIT: 'receipts', CONTABILITATE: 'invoices' };
const catalogForms = {
  'new-product': { kind: 'product', list: 'products', title: 'Produs nou' },
  'new-supplier': { kind: 'supplier', list: 'suppliers', title: 'Furnizor nou' },
};
const menus = { ADMIN: ['users'], ACHIZITII: ['orders', 'receipts', 'pending', 'stock', 'products', 'suppliers', 'overdue', 'notifications'], DEPOZIT: ['receipts', 'pending', 'orders', 'stock', 'products', 'suppliers', 'overdue', 'notifications'], CONTABILITATE: ['invoices', 'orders', 'receipts', 'pending', 'stock', 'products', 'suppliers', 'overdue', 'notifications'] };
const dateText = (value) => value ? new Intl.DateTimeFormat('ro-RO', { dateStyle: 'medium' }).format(new Date(value)) : '—';
const dateTimeText = (value) => value ? new Intl.DateTimeFormat('ro-RO', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—';

function Brand({ light = false }) {
  return <div className={`brand ${light ? 'brand-light' : ''}`}><span className="brand-logo-frame"><img className="brand-logo" src={rurisLogo} alt="RURIS" width="238" height="124" decoding="async" /></span><small>PORTAL INTERN</small></div>;
}

function Status({ value }) {
  return <span className={`status status-${value?.toLowerCase()}`}>{states[value] || value}</span>;
}

function DeliveryStatus({ value }) {
  const labels = { NOT_RECEIVED: 'Nelivrată', PARTIAL: 'Parțială', COMPLETE: 'Completă' };
  return value ? <span className={`status status-${value.toLowerCase()}`}>{labels[value] || value}</span> : '—';
}

function Login({ onLogin, notice }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError('');
    try {
      const result = await api('/auth/login', { method: 'POST', body: { email: email.trim(), password } });
      setPassword(''); onLogin(result.user);
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  return <main className="login-page">
    <section className="login-story"><Brand light /><div className="story-copy"><h1>Portal Intern<br /><span>RURIS</span></h1></div><footer>RURIS</footer></section>
    <section className="login-form-panel"><div className="login-card"><div className="login-symbol"><ArrowDownLeft size={25} /></div><h2>Intră în contul tău</h2>
      {notice && <div className="notice" role="status">{notice}</div>}
      <form onSubmit={submit}><label htmlFor="email">Adresă de email</label><input id="email" type="email" autoComplete="username" placeholder="nume@companie.ro" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} />
        <label htmlFor="password">Parolă</label><div className="password-field"><input id="password" type={visible ? 'text' : 'password'} autoComplete="current-password" placeholder="Introdu parola" required value={password} onChange={(event) => setPassword(event.target.value)} /><button type="button" className="icon-button" aria-label={visible ? 'Ascunde parola' : 'Arată parola'} aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={19} /> : <Eye size={19} />}</button></div>
        {error && <div className="error-message" role="alert"><CircleAlert size={18} />{error}</div>}
        <button className="button button-primary login-submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={18} /> : <>Autentificare <ArrowRight size={18} /></>}</button>
      </form><div className="login-help"><ShieldCheck size={20} /><p>Ai nevoie de acces? Contactează administratorul.</p></div>
    </div><footer>Portal Intern RURIS</footer></section>
  </main>;
}

function useData(path, onExpired, refresh) {
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setState({ loading: true });
    api(path, { signal: controller.signal }).then((data) => setState({ loading: false, data })).catch((error) => {
      if (error.name === 'AbortError') return;
      if (error.status === 401 || error.status === 422) onExpired();
      else setState({ loading: false, error: error.message });
    });
    return () => controller.abort();
  }, [path, onExpired, refresh]);
  return state;
}

function Feedback({ state, empty = 'Nu există înregistrări de afișat.' }) {
  if (state.loading) return <div className="feedback" role="status"><LoaderCircle className="spin" size={22} />Se încarcă informațiile…</div>;
  if (state.error) return <div className="feedback error-message" role="alert"><CircleAlert size={22} />{state.error}</div>;
  return <div className="feedback"><ClipboardList size={28} /><strong>{empty}</strong></div>;
}

function OrderDelivery({ id, onExpired, refresh }) {
  const [attempt, setAttempt] = useState(0);
  const state = useData(`/purchase-orders/${id}/delivery`, onExpired, refresh + attempt);
  if (state.loading || state.error) return <section><Feedback state={state} />{state.error && <button className="button button-secondary" onClick={() => setAttempt((value) => value + 1)}>Reîncarcă livrarea</button>}</section>;
  const delivery = state.data.delivery;
  return <section aria-label="Situația livrării"><h3>Livrare <DeliveryStatus value={delivery.delivery_status} /></h3>
    <div className="table-scroll"><table><thead><tr><th scope="col">Produs</th><th scope="col">Comandat</th><th scope="col">Acceptat</th><th scope="col">Rest de livrat</th><th scope="col">Unitate</th><th scope="col">Livrare</th></tr></thead><tbody>{delivery.items.map((item) => <tr key={item.id}><td>{item.description}</td><td>{quantity(item.quantity)}</td><td>{quantity(item.accepted_quantity)}</td><td>{quantity(item.remaining_quantity)}</td><td>{item.unit}</td><td><DeliveryStatus value={item.delivery_status} /></td></tr>)}</tbody></table></div>
  </section>;
}

function columnsFor(view, role) {
  if (view === 'users') return [['name', 'Nume'], ['email', 'Email'], ['role', 'Echipă'], ['is_active', 'Acces']];
  if (view === 'products') return [['sku', 'Cod produs'], ['name', 'Produs'], ['unit', 'Unitate'], ['is_active', 'Stare']];
  if (view === 'suppliers') return [['name', 'Furnizor'], ...(role === 'DEPOZIT' ? [] : [['tax_identity', 'Cod fiscal'], ['email', 'Email']]), ['is_active', 'Stare']];
  if (view === 'stock') return [['sku', 'Cod produs'], ['name', 'Produs'], ['quantity', 'Disponibil'], ['unit', 'Unitate']];
  if (view === 'overdue') return [['order_number', 'Comandă'], ['supplier_name', 'Furnizor'], ['description', 'Produs'], ['quantity', 'Comandat'], ['accepted_quantity', 'Acceptat'], ['remaining_quantity', 'Rest de livrat'], ['unit', 'Unitate'], ['expected_date', 'Termen'], ['days_overdue', 'Zile întârziere']];
  if (view === 'invoices') return [['reference', 'Factură'], ['supplier_id', 'Furnizor'], ['invoice_date', 'Data facturii'], ['total_amount', 'Total'], ['status', 'Stare']];
  if (view === 'receipts' || view === 'pending') return [['number', 'Recepție'], ['supplier_name', 'Furnizor'], ['delivery_reference', 'Aviz / document'], ['received_at', 'Data recepției'], ['pending_count', 'Poziții în așteptare'], ['status', 'Stare']];
  return [['number', 'Comandă'], ['supplier_id', 'Furnizor'], ['currency', 'Monedă'], ['status', 'Stare'], ['delivery_status', 'Livrare']];
}

function cell(row, field) {
  if (field === 'tax_identity') return row.tax_id ? `${row.tax_country || ''}${row.tax_id}` : '—';
  if (field === 'delivery_status') return <DeliveryStatus value={row[field]} />;
  if (field === 'status') return <Status value={row[field]} />;
  if (field === 'is_active') return <span className={`active-label ${row.is_active ? '' : 'inactive'}`}><i />{row.is_active ? 'Activ' : 'Inactiv'}</span>;
  if (field === 'role') return roles[row.role] || row.role;
  if (field === 'reference') return [row.series, row.number].filter(Boolean).join(' ');
  if (field.endsWith('_date') || field === 'received_at') return dateText(row[field]);
  if (field === 'supplier_id') return `Furnizor #${row[field]}`;
  if (field === 'total_amount') return `${price(row[field])} ${row.currency}`;
  if (field.includes('quantity')) return quantity(row[field]);
  return row[field] ?? '—';
}

function price(value) {
  if (value === undefined || value === null) return '—';
  const [whole, decimals = ''] = String(value).split('.');
  return `${whole},${decimals.replace(/0+$/, '').padEnd(2, '0')}`;
}

function searchText(value) {
  return value && typeof value === 'object' ? Object.values(value).map(searchText).join(' ') : String(value ?? '');
}

function OrdersTable({ rows, role, onDetail }) {
  const financial = ['ACHIZITII', 'CONTABILITATE'].includes(role);
  return <div className="table-scroll"><table className="orders-table"><thead><tr><th scope="col">Comandă</th><th scope="col">Furnizor</th><th scope="col">Produs comandat</th><th scope="col">Cantitate</th><th scope="col">Unitate</th>{financial && <th scope="col">Preț unitar fără TVA</th>}<th scope="col">Stare</th><th scope="col">Livrare</th><th scope="col"><span className="sr-only">Detalii</span></th></tr></thead>
    {rows.map((order) => {
      const lines = order.items?.length ? order.items : [null];
      return <tbody key={order.id} aria-label={`Comandă ${order.number}`}>{lines.map((line, index) => <tr key={line?.id ?? index}>
        {index === 0 && <><td rowSpan={lines.length}>{order.number}</td><td rowSpan={lines.length} className="order-supplier">{order.supplier_name || '—'}</td></>}
        <td className="order-product">{line?.description || '—'}{line?.sku && <small>{line.sku}</small>}</td><td>{quantity(line?.quantity)}</td><td>{line?.unit || '—'}</td>
        {financial && <td>{line?.unit_price !== undefined ? `${price(line.unit_price)} ${order.currency}` : '—'}</td>}
        {index === 0 && <><td rowSpan={lines.length}><Status value={order.status} /></td><td rowSpan={lines.length}><DeliveryStatus value={order.delivery_status} /></td><td rowSpan={lines.length}><button className="table-detail" aria-label={`Detalii comandă ${order.number}`} onClick={() => onDetail(order.id)}><ArrowRight size={17} /></button></td></>}
      </tr>)}</tbody>;
    })}
  </table></div>;
}

function RecordsTable({ rows, view, role, onDetail }) {
  if (view === 'orders') return <OrdersTable rows={rows} role={role} onDetail={onDetail} />;
  if (['receipts', 'pending', 'invoices'].includes(view)) return <DocumentLinesTable rows={rows} view={view} onDetail={onDetail} cell={cell} quantity={quantity} price={price} />;
  const columns = columnsFor(view, role);
  return <div className="table-scroll"><table><thead><tr>{columns.map(([key, label]) => <th key={key} scope="col">{label}</th>)}{onDetail && <th scope="col"><span className="sr-only">Detalii</span></th>}</tr></thead><tbody>{rows.map((row, index) => <tr key={`${row.id ?? row.order_item_id ?? index}`}>
    {columns.map(([key]) => <td key={key}>{cell(row, key)}</td>)}{onDetail && <td><button className="table-detail" aria-label={`Detalii ${views[view].singular.toLowerCase()} ${row.number}`} onClick={() => onDetail(row.id)}><ArrowRight size={17} /></button></td>}
  </tr>)}</tbody></table></div>;
}

function Detail({ summary, view, id, role, onClose, onExpired, onConfirmed }) {
  const [refresh, setRefresh] = useState(0);
  const [confirmedDocument, setConfirmedDocument] = useState(null);
  const [invoiceEditing, setInvoiceEditing] = useState(false);
  const [operationNotice, setOperationNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [requiresReload, setRequiresReload] = useState(false);
  const submitting = useRef(false);
  const state = useData(`${views[view].endpoint}/${id}`, onExpired, refresh);
  const document = confirmedDocument || (state.data && (state.data.order || state.data.receipt || state.data.invoice));
  const canConfirm = view === 'orders' && role === 'ACHIZITII' && document?.status === 'DRAFT';
  async function confirm() {
    if (submitting.current || requiresReload || !canConfirm) return;
    submitting.current = true; setBusy(true); setError('');
    try {
      const result = await api(`/purchase-orders/${id}/confirm`, { method: 'POST', body: { version: document.version } });
      setConfirmedDocument(result.order); onConfirmed();
    } catch (failure) {
      if ([401, 422].includes(failure.status)) onExpired();
      else if (failure.status === 0 || failure.status >= 500) {
        setError('Confirmarea nu a putut fi verificată. Actualizează datele înainte să încerci din nou.'); setRequiresReload(true);
      } else {
        setError(failure.message); setRequiresReload(failure.status === 409);
      }
    } finally { submitting.current = false; setBusy(false); }
  }
  function reload() {
    setConfirmedDocument(null); setOperationNotice(''); setError(''); setRequiresReload(false); setRefresh((value) => value + 1);
    onConfirmed();
  }
  useEffect(() => {
    const previousFocus = window.document.activeElement;
    const dialog = window.document.getElementById('document-dialog');
    dialog.showModal();
    return () => { dialog.close(); previousFocus?.focus(); };
  }, []);
  return <dialog id="document-dialog" onCancel={(event) => { if (submitting.current) event.preventDefault(); else onClose(); }} aria-labelledby="detail-title" aria-busy={busy}><div className="dialog-heading"><div><span className="eyebrow muted">DETALIU DOCUMENT</span><h2 id="detail-title">{views[view].singular} {view === 'invoices' && document ? [document.series, document.number].filter(Boolean).join(' ') : document?.number || `#${id}`}</h2></div><button className="icon-button" aria-label="Închide detaliile" disabled={busy} onClick={onClose}><X /></button></div>
    {!document ? <Feedback state={state} /> : <fieldset className="document-body" disabled={busy}><div className="document-facts">{(document.supplier_name || summary?.supplier_name) && <p><span>Furnizor</span><strong>{document.supplier_name || summary.supplier_name}</strong></p>}{view === 'receipts' && <><p><span>Aviz / document</span><strong>{document.delivery_reference || '—'}</strong></p><p><span>Data recepției</span><strong>{dateTimeText(document.received_at)}</strong></p></>}{view === 'invoices' && <><p><span>Data facturii</span><strong>{dateText(document.invoice_date)}</strong></p><p><span>Scadență</span><strong>{dateText(document.due_date)}</strong></p></>}</div><div className="document-meta"><Status value={document.status} /><span>Versiunea {document.version}</span>{document.currency && <span>{document.currency}</span>}</div>
      {view === 'invoices' ? <InvoiceWorkflow invoice={document} onEditingChange={setInvoiceEditing} onExpired={onExpired} onChanged={(updated) => { setConfirmedDocument(updated); setOperationNotice(''); onConfirmed(); }} onBusyChange={(value) => { submitting.current = value; setBusy(value); }} /> : view === 'orders' && ['CONFIRMED', 'CLOSED'].includes(document.status) ? <OrderDelivery id={id} onExpired={onExpired} refresh={refresh} /> : <><h3>Pozițiile documentului</h3>{document.items?.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Produs</th><th scope="col">Cantitate</th><th scope="col">Unitate</th>{view === 'receipts' && <><th scope="col">Acceptat</th><th scope="col">Respins</th><th scope="col">În așteptare</th></>}</tr></thead><tbody>{document.items.map((item) => <tr key={item.id}><td>{item.description}</td><td>{quantity(item.quantity ?? item.received_quantity)}</td><td>{item.unit}</td>{view === 'receipts' && <><td>{quantity(item.total_accepted_quantity ?? item.accepted_quantity)}</td><td>{quantity(item.rejected_quantity)}</td><td>{quantity(item.pending_quantity)}</td></>}</tr>)}</tbody></table></div> : <p className="muted">Documentul nu are poziții.</p>}</>}
      {view === 'orders' && ['ACHIZITII', 'CONTABILITATE'].includes(role) && <AmountsPreview lines={document.items || []} currency={document.currency} title="Valoare comandă" />}
      {(operationNotice || confirmedDocument && view === 'orders') && <div className="notice success-notice" role="status">{operationNotice || 'Comanda a fost confirmată.'}</div>}
      {view === 'receipts' && role === 'DEPOZIT' && document.status === 'DRAFT' && <ReceiptConfirmation key={`${document.id}-${document.version}`} receipt={document} onExpired={onExpired} onConfirmed={(receipt) => { setConfirmedDocument(receipt); setOperationNotice('Recepția a fost confirmată.'); onConfirmed(); }} onBusyChange={(value) => { submitting.current = value; setBusy(value); }} onReload={reload} />}
      {view === 'receipts' && document.status === 'CONFIRMED' && <ReceiptPendingWorkflow key={`${document.id}-${document.version}`} receipt={document} role={role} onExpired={onExpired} onChanged={(receipt, notice) => { setConfirmedDocument(receipt); setOperationNotice(notice); onConfirmed(); }} onBusyChange={(value) => { submitting.current = value; setBusy(value); }} onReload={reload} />}
      {!invoiceEditing && ['orders', 'invoices'].includes(view) && <DocumentHistory kind={view === 'orders' ? 'order' : 'invoice'} id={document.id} version={document.version} onExpired={onExpired} />}
      {!invoiceEditing && (view !== 'orders' || role !== 'DEPOZIT') && <DocumentAttachments kind={view} document={document} onExpired={onExpired} onReload={reload} onChanged={(updated, notice) => { setConfirmedDocument(updated); setOperationNotice(notice); onConfirmed(); }} onBusyChange={(value) => { submitting.current = value; setBusy(value); }} />}
      {error && <div className="error-message" role="alert"><CircleAlert size={18} />{error}</div>}
      {(canConfirm || requiresReload) && <div className="document-actions">
        {requiresReload && <button className="button button-secondary" onClick={reload}><RefreshCw size={16} />Actualizează datele</button>}
        {canConfirm && <button className="button button-primary" disabled={busy || requiresReload} onClick={confirm}>{busy ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}{busy ? 'Se confirmă…' : 'Confirmă comanda'}</button>}
      </div>}
    </fieldset>}
  </dialog>;
}

function Records(props) {
  return props.view === 'notifications' ? <Notifications onExpired={props.onExpired} refresh={props.refresh} /> : <RecordsList {...props} />;
}

function RecordsList({ view, role, onExpired, compact = false, onNavigate, refresh }) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [detailId, setDetailId] = useState(null);
  const [revision, setRevision] = useState(0);
  const config = views[view];
  const state = useData(`${config.endpoint}?page=${page}&per_page=${compact ? 5 : 20}`, onExpired, refresh + revision);
  const rows = state.data?.[config.key] || [];
  const filtered = rows.filter((row) => searchText(row).toLocaleLowerCase('ro').includes(search.toLocaleLowerCase('ro')));
  const total = state.data?.total ?? 0;
  return <section className="panel records-panel"><div className="panel-heading"><div><h2>{config.label}</h2>{!compact && <p>{view === 'pending' ? `${total} recepții cu marfă în așteptare` : `${total} înregistrări`}</p>}</div>{compact ? <button className="text-button" onClick={() => onNavigate(view)}>Vezi toate <ArrowRight size={15} /></button> : <label className="search-field"><Search size={17} /><span className="sr-only">Caută pe pagina curentă</span><input placeholder="Caută pe această pagină…" value={search} onChange={(event) => setSearch(event.target.value)} /></label>}</div>
    {state.loading || state.error || !rows.length ? <Feedback state={state} empty={view === 'pending' ? 'Nu există recepții cu marfă în așteptare.' : undefined} /> : filtered.length ? <RecordsTable rows={filtered} view={view} role={role} onDetail={config.singular ? setDetailId : null} /> : <div className="feedback">Niciun rezultat pe această pagină. Încearcă alt termen.</div>}
    {view === 'pending' && !state.loading && !state.error && !rows.length && <div className="pending-empty-actions"><p>Emailurile trimise se consultă în Notificări.</p>{onNavigate && <button type="button" className="text-button" onClick={() => onNavigate('notifications')}>Vezi notificările</button>}</div>}
    {!compact && !state.error && total > 0 && <div className="pagination"><span>Pagina {page} din {Math.ceil(total / 20)}</span><div><button className="icon-button" aria-label="Pagina anterioară" disabled={page <= 1 || state.loading} onClick={() => { setPage(page - 1); setSearch(''); }}><ChevronLeft size={18} /></button><button className="icon-button" aria-label="Pagina următoare" disabled={page * 20 >= total || state.loading} onClick={() => { setPage(page + 1); setSearch(''); }}><ChevronRight size={18} /></button></div></div>}
    {detailId !== null && <Detail summary={rows.find((row) => row.id === detailId)} view={view === 'pending' ? 'receipts' : view} id={detailId} role={role} onClose={() => setDetailId(null)} onExpired={onExpired} onConfirmed={() => setRevision((value) => value + 1)} />}
  </section>;
}

function Overview({ user, onExpired, onNavigate, refresh }) {
  const view = primary[user.role];
  const docs = useData(`${views[view].endpoint}?per_page=1`, onExpired, refresh);
  const overdue = useData(user.role === 'ADMIN' ? null : '/purchase-orders/overdue?per_page=5', onExpired, refresh);
  const products = useData(user.role === 'ADMIN' ? null : '/products?per_page=1', onExpired, refresh);
  const pending = useData(user.role === 'ADMIN' ? null : '/receipts/pending?per_page=1', onExpired, refresh);
  const metrics = [[views[view].label, docs, views[view].icon, 'Înregistrări în aplicație'], ...(user.role === 'ADMIN' ? [] : [['Poziții întârziate', overdue, CircleAlert, 'Cu rest de livrat'], ['Produse în catalog', products, Package, 'Catalogul comun'], ['Recepții de clarificat', pending, CircleAlert, 'Cu marfă în așteptare']])];
  return <><div className="welcome-banner"><div><h2>Portal Intern RURIS</h2><p>Bună, {user.name.split(' ')[0]}.</p></div><div className="banner-symbol" aria-hidden="true"><Boxes size={68} strokeWidth={1} /></div></div>
    <div className="metrics">{metrics.map(([label, state, Icon, caption]) => <section className="metric" key={label}><div className="metric-top"><span>{label}</span><Icon size={20} /></div><strong>{state.loading ? '…' : state.error ? '—' : state.data?.total ?? '—'}</strong><small>{state.error ? 'Date indisponibile momentan' : caption}</small></section>)}</div>
    <div className={`overview-grid ${user.role === 'ADMIN' ? 'admin-grid' : ''}`}><Records view={view} role={user.role} compact onNavigate={onNavigate} onExpired={onExpired} refresh={refresh} />{user.role !== 'ADMIN' && <aside className="panel attention-panel"><div className="panel-heading"><div><span className="section-icon"><CircleAlert size={17} /></span><h2>De urmărit</h2><p>Termene depășite</p></div></div>
      {overdue.loading || overdue.error ? <Feedback state={overdue} /> : overdue.data?.items?.length ? <div className="attention-list">{overdue.data.items.map((item, index) => <div className="attention-item" key={index}><span className="late-dot" /><div><strong>{item.description}</strong><p>{item.order_number} · {quantity(item.remaining_quantity)} {item.unit}</p><small>{item.days_overdue} zile întârziere</small></div></div>)}</div> : <div className="calm-state"><span><Check size={23} /></span><strong>Nicio întârziere</strong></div>}
      <button className="attention-footer" onClick={() => onNavigate('overdue')}>Vezi toate întârzierile <ArrowRight size={16} /></button></aside>}</div>
  </>;
}

function Workspace({ user, onExpired, onLogout }) {
  const [view, setView] = useState('overview');
  const [mobileMenu, setMobileMenu] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const navigate = (next) => { setView(next); setMobileMenu(false); };
  async function logout() {
    setLoggingOut(true); setError('');
    try { await api('/auth/logout', { method: 'POST' }); onLogout(); }
    catch (failure) { if (failure.status === 401 || failure.status === 422) onLogout(); else setError(failure.message); }
    finally { setLoggingOut(false); }
  }
  const catalogForm = catalogForms[view];
  const activeView = catalogForm?.list || (view === 'new-invoice' ? 'invoices' : view === 'new-order' ? 'orders' : view === 'new-receipt' ? 'receipts' : view === 'new-user' ? 'users' : view);
  const title = catalogForm?.title || (view === 'overview' ? 'Privire de ansamblu' : view === 'new-invoice' ? 'Factură nouă' : view === 'new-order' ? 'Comandă nouă' : view === 'new-receipt' ? 'Recepție nouă' : view === 'new-user' ? 'Utilizator nou' : views[view].label);
  return <div className="workspace"><a className="skip-link" href="#main-content">Sari la conținut</a>{mobileMenu && <button className="menu-backdrop" aria-label="Închide meniul" onClick={() => setMobileMenu(false)} />}
    <aside className={`sidebar ${mobileMenu ? 'sidebar-open' : ''}`}><Brand light /><div className="workspace-tag"><i />Portal intern</div><nav aria-label="Navigare principală"><span className="nav-label">GENERAL</span><button className={view === 'overview' ? 'nav-link selected' : 'nav-link'} onClick={() => navigate('overview')} aria-current={view === 'overview' ? 'page' : undefined}><LayoutDashboard size={19} />Privire de ansamblu</button><span className="nav-label nav-label-second">{user.role === 'ADMIN' ? 'ADMINISTRARE' : 'OPERAȚIUNI'}</span>{menus[user.role].map((key) => { const Icon = views[key].icon; return <button key={key} className={(activeView === key) ? 'nav-link selected' : 'nav-link'} onClick={() => navigate(key)} aria-current={activeView === key ? 'page' : undefined}><Icon size={19} />{views[key].label}</button>; })}</nav></aside>
    <div className="workspace-main"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-toggle" aria-label="Deschide meniul" aria-expanded={mobileMenu} onClick={() => setMobileMenu(!mobileMenu)}><Menu size={21} /></button><span>Operațiuni</span><ChevronRight size={14} /><strong>{title}</strong></div><div className="account"><span className="role-chip">{roles[user.role]}</span><span className="avatar">{user.name.charAt(0).toLocaleUpperCase('ro')}</span><div className="account-name"><strong>{user.name}</strong><small>{roles[user.role]}</small></div><button className="icon-button logout-button" aria-label="Deconectare" title="Deconectare" disabled={loggingOut} onClick={logout}>{loggingOut ? <LoaderCircle size={19} className="spin" /> : <LogOut size={19} />}</button></div></header>
      <main id="main-content" className="page-content"><div className="page-heading"><div><span className="eyebrow muted">RURIS / {roles[user.role].toLocaleUpperCase('ro')}</span><h1>{title}</h1></div><div className="page-actions">{user.role === 'CONTABILITATE' && ['overview', 'invoices'].includes(view) && <button className="button button-primary" onClick={() => { setNotice(''); navigate('new-invoice'); }}>Factură nouă</button>}{user.role === 'DEPOZIT' && ['overview', 'receipts'].includes(view) && <button className="button button-primary" onClick={() => { setNotice(''); navigate('new-receipt'); }}>Recepție nouă</button>}{user.role === 'ACHIZITII' && ['products', 'suppliers'].includes(view) && <button className="button button-primary" onClick={() => { setNotice(''); navigate(view === 'products' ? 'new-product' : 'new-supplier'); }}>{view === 'products' ? 'Produs nou' : 'Furnizor nou'}</button>}{user.role === 'ADMIN' && ['overview', 'users'].includes(view) && <button className="button button-primary" onClick={() => { setNotice(''); navigate('new-user'); }}>Utilizator nou</button>}{user.role === 'ACHIZITII' && ['overview', 'orders'].includes(view) && <button className="button button-primary" onClick={() => { setNotice(''); navigate('new-order'); }}>Comandă nouă</button>}{!catalogForm && !['new-order', 'new-user', 'new-receipt', 'new-invoice'].includes(view) && <button className="button button-secondary" onClick={() => setRefresh(refresh + 1)}><RefreshCw size={16} />Actualizează</button>}</div></div>
        {error && <div className="error-message" role="alert">{error}</div>}{notice && <div className="notice success-notice" role="status">{notice}<button className="icon-button" aria-label="Închide mesajul" onClick={() => setNotice('')}><X size={16} /></button></div>}{catalogForm && user.role === 'ACHIZITII' ? <CatalogForm key={view} kind={catalogForm.kind} onExpired={onExpired} onCancel={() => navigate(catalogForm.list)} onCreated={(record) => { setNotice(`${catalogForm.kind === 'product' ? 'Produsul' : 'Furnizorul'} ${record.name} a fost salvat.`); setRefresh((value) => value + 1); navigate(catalogForm.list); }} /> : view === 'new-invoice' && user.role === 'CONTABILITATE' ? <InvoiceForm onExpired={onExpired} onCancel={() => navigate('invoices')} onCreated={(invoice) => { setNotice(`Factura ${[invoice.series, invoice.number].filter(Boolean).join(' ')} a fost salvată ca ciornă.`); setRefresh((value) => value + 1); navigate('invoices'); }} /> : view === 'new-receipt' && user.role === 'DEPOZIT' ? <ReceiptForm onExpired={onExpired} onCancel={() => navigate('receipts')} onCreated={(receipt) => { setNotice(`Recepția ${receipt.number} a fost salvată ca ciornă.`); setRefresh((value) => value + 1); navigate('receipts'); }} /> : view === 'new-user' && user.role === 'ADMIN' ? <UserForm onExpired={onExpired} onCancel={() => navigate('users')} onCreated={(account) => { setNotice(`Utilizatorul ${account.name} a fost creat.`); setRefresh((value) => value + 1); navigate('users'); }} /> : view === 'overview' ? <Overview user={user} onExpired={onExpired} onNavigate={navigate} refresh={refresh} /> : view === 'new-order' && user.role === 'ACHIZITII' ? <OrderForm onExpired={onExpired} onCancel={() => navigate('orders')} onCreated={(order) => { setNotice(`Comanda ${order.number} a fost salvată ca ciornă.`); setRefresh((value) => value + 1); navigate('orders'); }} /> : <Records key={view} view={view} role={user.role} onExpired={onExpired} refresh={refresh} onNavigate={navigate} />}
        <footer className="page-footer"><span>Portal Intern RURIS</span></footer>
      </main></div></div>;
}

export default function App() {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState('');
  const [notice, setNotice] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setBooting(true); setBootError('');
    api('/auth/me', { signal: controller.signal }).then((data) => setUser(data.user)).catch((error) => {
      if (error.name !== 'AbortError' && ![401, 422].includes(error.status)) setBootError(error.message);
    }).finally(() => { if (!controller.signal.aborted) setBooting(false); });
    return () => controller.abort();
  }, [attempt]);
  const expired = useCallback(() => { setUser(null); setNotice('Sesiunea a expirat. Autentifică-te din nou.'); }, []);
  if (booting) return <div className="boot-screen"><Brand /><LoaderCircle size={24} className="spin" /><p>Se încarcă…</p></div>;
  if (bootError) return <div className="boot-screen"><Brand /><p role="alert">{bootError}</p><button className="button button-primary" onClick={() => setAttempt(attempt + 1)}>Încearcă din nou</button></div>;
  if (!user) return <Login notice={notice} onLogin={(account) => { setUser(account); setNotice(''); }} />;
  if (!menus[user.role]) return <div className="boot-screen"><p role="alert">Rolul contului nu este recunoscut. Contactează administratorul.</p></div>;
  return <Workspace key={`${user.id}-${user.role}`} user={user} onExpired={expired} onLogout={() => { setUser(null); setNotice('Te-ai deconectat cu succes.'); }} />;
}
