import { parseQuantity, quantityDifference, quantityText } from './receiptQuantities.js';
import { calculateLine } from './amounts.js';

export default function InvoiceSourceNotice({ line, currency }) {
  const source = line.source;
  if (!source) return null;
  const amount = parseQuantity(line.quantity);
  const available = parseQuantity(source.available_quantity);
  return <div className="source-notice">
    {source.registered_quantity !== undefined && <p className="field-hint">Înregistrat pe facturi: {quantityText(source.registered_quantity)} {source.unit} · Rest neînregistrat din comandă: {quantityText(source.remaining_to_invoice)} {source.unit}.</p>}
    {amount && source.remaining_to_invoice !== undefined && amount.thousandths > (parseQuantity(source.remaining_to_invoice)?.thousandths ?? 0n)
      && <p className="quantity-balance balance-warning">Cantitatea introdusă depășește restul neînregistrat al comenzii. Posibilă factură duplicată; verifică documentele existente.</p>}
    <p className="field-hint">În comandă: preț fără TVA {String(source.unit_price).replace('.', ',')} {source.currency || currency} · TVA {String(source.vat_rate).replace('.', ',')}%.</p>
    {calculateLine(line) && (quantityText(line.unit_price) !== quantityText(source.unit_price) || quantityText(line.vat_rate) !== quantityText(source.vat_rate)
      || source.currency && source.currency !== currency) && <p className="quantity-balance balance-warning">Prețul, TVA sau moneda diferă de comandă. Verifică documentul furnizorului înainte de asociere.</p>}
    {amount && available && amount.thousandths > available.thousandths && <p className="quantity-balance balance-warning">
      Cantitate fără marfă disponibilă pentru asociere: {quantityDifference(line.quantity, source.available_quantity)} {source.unit}.
    </p>}
  </div>;
}
