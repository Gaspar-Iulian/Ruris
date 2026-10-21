import { calculateLine, calculateTotals, moneyText } from './amounts.js';

export function LineAmounts({ line, currency }) {
  const amounts = calculateLine(line);
  return <div className="line-amounts" aria-label="Valori poziție">
    <span>Net <strong>{moneyText(amounts?.net_amount, currency)}</strong></span>
    <span>TVA <strong>{moneyText(amounts?.vat_amount, currency)}</strong></span>
    <span>Total <strong>{moneyText(amounts?.total_amount, currency)}</strong></span>
  </div>;
}

export default function AmountsPreview({ lines, currency, title = 'Total calculat' }) {
  const amounts = calculateTotals(lines);
  return <section className="panel amounts-preview" aria-label={title}><h2>{title}</h2>
    <div className="amounts-grid">{[['net_amount', 'Net fără TVA'], ['vat_amount', 'TVA'], ['total_amount', 'Total cu TVA']].map(([key, label]) =>
      <div key={key}><span>{label}</span><strong>{moneyText(amounts?.[key], currency)}</strong></div>)}</div>
    {!amounts && <p className="field-hint">Completează cantitatea, prețul și TVA pentru toate pozițiile, în limitele permise.</p>}
  </section>;
}
