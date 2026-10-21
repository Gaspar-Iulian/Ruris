export const emptyTotals = () => ({ net_amount: '', vat_amount: '', total_amount: '' });

export function readTotals(values) {
  if (Object.values(values).every((value) => !value.trim())) return null;
  const result = {};
  for (const [key, value] of Object.entries(values)) {
    const normalized = value.trim().replace(',', '.');
    if (!/^[0-9]{1,16}(?:\.[0-9]{1,2})?$/.test(normalized)) throw new Error('Completează toate cele trei totaluri, cu valori nenegative și maximum două zecimale.');
    result[key] = normalized;
  }
  return result;
}

export default function DeclaredTotals({ values, onChange, currency }) {
  return <section className="panel order-header declared-totals-fields"><h2>Totaluri din document ({currency})</h2>
    <p className="field-hint">Introdu sumele înscrise de furnizor. Sunt necesare pentru verificarea facturii.</p>
    <div className="user-form-grid">{[['net_amount', 'Net factură'], ['vat_amount', 'TVA factură'], ['total_amount', 'Total factură']].map(([key, label]) =>
      <div className="form-field" key={key}><label htmlFor={`declared-${key}`}>{label}</label><input id={`declared-${key}`} inputMode="decimal" maxLength={19} value={values[key]} onChange={(event) => onChange({ ...values, [key]: event.target.value })} /></div>)}</div>
  </section>;
}
