import { quantityText } from './receiptQuantities.js';

const deliveries = { NOT_RECEIVED: 'Nerecepționată', PARTIAL: 'Livrată parțial', COMPLETE: 'Livrată complet' };
const dateText = (value) => value ? new Intl.DateTimeFormat('ro-RO').format(new Date(`${value}T12:00:00`)) : '—';

export function orderOptionLabel(order) {
  const first = order.items?.[0];
  return [order.number, order.supplier_name,
    first && `${first.description} · ${quantityText(first.quantity)} ${first.unit}`,
    order.items?.length > 1 && `+${order.items.length - 1} poziții`, deliveries[order.delivery_status]].filter(Boolean).join(' — ');
}

export function SelectedOrderSummary({ order, choice, financial = false }) {
  if (!order) return null;
  return <section className="selected-order-summary" aria-label="Comanda selectată">
    <h3>{order.number} · {order.supplier_name || choice?.supplier_name}</h3>
    <p>{deliveries[order.delivery_status || choice?.delivery_status] || 'Confirmată'}{financial && order.currency ? ` · ${order.currency}` : ''}</p>
    <ul>{order.items.map((line) => <li key={line.id}>
      <strong>{line.description}</strong> · {quantityText(line.quantity)} {line.unit}
      {line.accepted_quantity != null && <> · Acceptat: {quantityText(line.accepted_quantity)}</>}
      {line.remaining_quantity != null && <> · Rest: {quantityText(line.remaining_quantity)}</>}
      {line.expected_date && <> · Termen: {dateText(line.expected_date)}</>}
      {financial && line.unit_price != null && <> · Preț: {String(line.unit_price).replace('.', ',')} {order.currency}/{line.unit}</>}
    </li>)}</ul>
  </section>;
}
