import { moneyText, parseMoney } from './amounts.js';

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

export default function DeclaredTotals({ values, onChange, currency, calculated }) {
  const keys = ['net_amount', 'vat_amount', 'total_amount'];
  const amounts = Object.fromEntries(keys.map((key) => [key, parseMoney(values[key])]));
  const complete = keys.every((key) => amounts[key] !== null);
  const entered = Object.values(values).some((value) => value.trim());
  const matches = complete && calculated && keys.every((key) => amounts[key] === calculated[key]);
  return <section className="panel order-header declared-totals-fields"><h2>Totaluri din document ({currency})</h2>
    <p className="field-hint">Introdu sumele înscrise de furnizor. Sunt necesare pentru verificarea facturii.</p>
    <div className="user-form-grid">{[['net_amount', 'Net factură'], ['vat_amount', 'TVA factură'], ['total_amount', 'Total factură']].map(([key, label]) =>
      <div className="form-field" key={key}><label htmlFor={`declared-${key}`}>{label}</label><input id={`declared-${key}`} inputMode="decimal" maxLength={19} value={values[key]} onChange={(event) => onChange({ ...values, [key]: event.target.value })} /></div>)}</div>
    {calculated && <div className="declared-comparison" role="region" aria-label="Verificare totaluri introduse" aria-live="polite">
      {!entered ? <p className="field-hint">Compară totalul calculat cu factura furnizorului și introdu sumele de pe document.</p>
        : !complete ? <p className="quantity-balance balance-warning">Completează toate cele trei sume pentru comparație.</p>
          : <><p className={`quantity-balance ${matches ? 'balance-ok' : 'balance-warning'}`}>{matches ? 'Totalurile corespund pozițiilor.' : 'Există diferențe față de pozițiile facturii.'}</p>
            {!matches && <div className="line-amounts">{[['net_amount', 'Diferență net'], ['vat_amount', 'Diferență TVA'], ['total_amount', 'Diferență total']].map(([key, label]) =>
              <span key={key}>{label} <strong>{moneyText(amounts[key] - calculated[key], currency)}</strong></span>)}</div>}
            {amounts.net_amount + amounts.vat_amount !== amounts.total_amount && <p className="quantity-balance balance-warning">Pe document, netul + TVA nu este egal cu totalul introdus.</p>}
          </>}
    </div>}
  </section>;
}
