import { quantityText } from './receiptQuantities.js';

const statuses = { DRAFT: 'Ciornă', BLOCKED: 'Blocată', VERIFIED: 'Verificată', APPROVED: 'Aprobată', PAID: 'Plătită', CANCELLED: 'Anulată' };

export default function ExistingOrderInvoices({ order }) {
  if (!order.invoice_documents?.length) return null;
  return <section className="existing-order-invoices" aria-label="Facturi existente pentru comandă">
    <h3>Facturi deja înregistrate pentru {order.number}</h3>
    <p className="quantity-balance balance-warning">Verifică documentele existente înainte să înregistrezi o nouă factură. Cantitățile includ și ciornele și facturile blocate. Facturile anulate nu consumă restul comenzii.</p>
    <div className="table-scroll"><table><thead><tr><th>Factură</th><th>Stare</th><th>Produse și cantități înregistrate</th></tr></thead>
      <tbody>{order.invoice_documents.map((invoice) => <tr key={invoice.id}>
        <td>{[invoice.series, invoice.number].filter(Boolean).join(' ')}</td><td>{statuses[invoice.status] || invoice.status}</td>
        <td>{invoice.items.map((item, index) => {
          const source = order.items.find((line) => line.id === item.purchase_order_item_id);
          return <p key={index}>{source?.description || 'Poziție comandă'} · {quantityText(item.quantity)} {source?.unit}{item.via_receipts && ' · asociat prin recepții'}</p>;
        })}</td>
      </tr>)}</tbody></table></div>
  </section>;
}
