import { ArrowRight } from 'lucide-react';

export default function DocumentLinesTable({ rows, view, onDetail, cell, quantity, price }) {
  const invoice = view === 'invoices';
  const documentName = invoice ? 'Factură' : 'Recepție';
  const columns = [
    { label: documentName, document: true, value: (row) => invoice ? cell(row, 'reference') : row.number },
    { label: 'Furnizor', document: true, wrap: true, value: (row) => row.supplier_name || '—' },
    ...(!invoice ? [{ label: 'Aviz / document', document: true, value: (row) => row.delivery_reference || '—' }] : []),
    { label: 'Produs', wrap: true, value: (_, line) => line?.description || '—' },
    { label: 'Comandă', value: (_, line) => line?.order_number || '—' },
    { label: invoice ? 'Cantitate' : 'Sosit', value: (_, line) => quantity(line?.[invoice ? 'quantity' : 'received_quantity']) },
    { label: 'Unitate', value: (_, line) => line?.unit || '—' },
    ...(invoice ? [
      { label: 'Preț unitar fără TVA', value: (row, line) => line?.unit_price == null ? '—' : `${price(line.unit_price)} ${row.currency}` },
      { label: 'TVA', value: (_, line) => line?.vat_rate == null ? '—' : `${String(line.vat_rate).replace('.', ',')}%` },
      { label: 'Total poziție', value: (row, line) => line?.total_amount == null ? '—' : `${price(line.total_amount)} ${row.currency}` },
      { label: 'Total factură', document: true, value: (row) => cell(row, 'total_amount') },
      { label: 'Data facturii', document: true, value: (row) => cell(row, 'invoice_date') },
      { label: 'Scadență', document: true, value: (row) => cell(row, 'due_date') },
    ] : [
      { label: 'Acceptat', value: (_, line) => quantity(line?.total_accepted_quantity) },
      { label: 'Respins', value: (_, line) => quantity(line?.rejected_quantity) },
      { label: 'În așteptare', value: (_, line) => quantity(line?.pending_quantity) },
      { label: 'Data recepției', document: true, value: (row) => cell(row, 'received_at') },
    ]),
    { label: 'Stare', document: true, value: (row) => cell(row, 'status') },
  ];
  return <div className="table-scroll"><table className="document-lines-table"><thead><tr>
    {columns.map((column) => <th key={column.label} scope="col">{column.label}</th>)}
    <th scope="col"><span className="sr-only">Detalii</span></th>
  </tr></thead>{rows.map((row) => {
    const source = row.line_items || [];
    const visible = view === 'pending' ? source.filter((line) => Number(line.pending_quantity) > 0) : source;
    const lines = visible.length ? visible : [null];
    return <tbody key={row.id} aria-label={`${documentName} ${invoice ? cell(row, 'reference') : row.number}`}>
      {lines.map((line, index) => <tr key={line?.id ?? index}>
        {columns.map((column) => column.document && index > 0 ? null : <td key={column.label}
          rowSpan={column.document ? lines.length : undefined} className={column.wrap ? 'document-description' : undefined}>
          {column.value(row, line)}
        </td>)}
        {index === 0 && <td rowSpan={lines.length}><button type="button" className="table-detail"
          aria-label={`Detalii ${invoice ? 'factură' : 'recepție'} ${row.number}`} onClick={() => onDetail(row.id)}><ArrowRight size={17} /></button></td>}
      </tr>)}
    </tbody>;
  })}</table></div>;
}
