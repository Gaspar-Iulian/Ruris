import { test, expect } from '@playwright/test';

async function portal(page, initialStatus = 'BLOCKED', failure) {
  let invoice = { id: 1, number: 'DUP-1', series: '', supplier_id: 1, supplier_name: 'Furnizor test',
    status: initialStatus, version: 3, currency: 'RON', invoice_date: '2026-10-21', due_date: '2026-11-21',
    net_amount: '75.00', vat_amount: '14.25', total_amount: '89.25', total_ron: '89.25', exchange_rate_source: 'IDENTITY',
    declared_totals: { net_amount: '75.00', vat_amount: '14.25', total_amount: '89.25' },
    totals_difference: { net_amount: '0.00', vat_amount: '0.00', total_amount: '0.00' },
    cancelled_at: null, cancelled_by_id: null, cancellation_reason: null,
    items: [{ id: 11, line_number: 1, description: 'Filtru', unit: 'BUC', quantity: '5.000', unit_price: '15.0000', vat_rate: '19.00' }] };
  const requests = [];
  await page.context().addCookies([{ name: 'csrf_access_token', value: 'cancel-csrf', domain: '127.0.0.1', path: '/' }]);
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/auth/me') return route.fulfill({ json: { user: { id: 19, role: 'CONTABILITATE', name: 'Contabil test' } } });
    if (path === '/api/invoices/1/cancel') {
      requests.push({ body: request.postDataJSON(), headers: request.headers() });
      if (failure) return route.fulfill({ status: failure, json: { message: 'Factura a fost modificată.' } });
      invoice = { ...invoice, status: 'CANCELLED', version: 4, cancelled_by_id: 19, cancelled_at: '2026-10-21T13:00:00Z',
        cancellation_reason: request.postDataJSON().reason, total_ron: null };
      return route.fulfill({ json: { invoice } });
    }
    if (path === '/api/invoices/1') return route.fulfill({ json: { invoice } });
    if (path === '/api/invoices/1/matching') return route.fulfill({ json: {
      invoice, items: invoice.items.map((item) => ({ ...item, allocated_quantity: '2.000', remaining_quantity: '3.000', candidates: [] })),
      allocations: invoice.status === 'CANCELLED' ? [] : [{ id: 1, invoice_item_id: 11, quantity: '2.000', receipt_number: 'REC-1', order_number: 'CA-1' }],
      issues: [],
    } });
    if (path.endsWith('/attachments')) return route.fulfill({ json: { attachments: [], total: 0, can_manage: !['CANCELLED', 'APPROVED', 'PAID'].includes(invoice.status) } });
    if (path.endsWith('/history')) return route.fulfill({ json: { total: 1, events: [{ id: 1, entity_type: 'invoices', action: 'CANCEL', actor_name: 'Contabil test',
      created_at: '2026-10-21T13:00:00Z', reason: 'Factura duplicata', before: { status: 'BLOCKED' }, after: { status: 'CANCELLED', cancellation_reason: 'Factura duplicata' } }] } });
    const records = {
      '/api/invoices': { invoices: [invoice], total: 1 }, '/api/products': { products: [], total: 0 },
      '/api/purchase-orders/overdue': { items: [], total: 0 }, '/api/receipts/pending': { receipts: [], total: 0 },
    };
    return route.fulfill({ json: records[path] || {} });
  });
  await page.goto('/');
  await page.getByRole('navigation').getByRole('button', { name: 'Facturi', exact: true }).click();
  await page.getByRole('button', { name: 'Detalii factură DUP-1', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Procesare factură' })).toBeVisible();
  return requests;
}

test('cancellation requires an explicit reason and retains a read-only document with history', async ({ page }) => {
  const requests = await portal(page);
  await page.getByRole('button', { name: 'Anulează factura', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Anulare factură' })).toContainText('Asocierile active vor fi eliberate');
  await page.getByRole('button', { name: 'Confirmă anularea', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Completează motivul anulării.');
  expect(requests).toHaveLength(0);
  await page.getByLabel('Motivul anulării', { exact: true }).fill(' Factura duplicata ');
  await page.getByRole('button', { name: 'Confirmă anularea', exact: true }).click();
  await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Anulată');
  await expect(page.getByRole('region', { name: 'Asocieri active' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Verifică factura', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Anulează factura', exact: true })).toHaveCount(0);
  expect(requests[0].body).toEqual({ version: 3, reason: 'Factura duplicata' });
  expect(requests[0].headers['x-csrf-token']).toBe('cancel-csrf');
  const history = page.getByRole('region', { name: 'Istoric factură' });
  await history.getByRole('button', { name: 'Istoric', exact: true }).click();
  await expect(history).toContainText('Factură anulată');
  await expect(history).toContainText('Factura duplicata');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

for (const status of ['APPROVED', 'PAID', 'CANCELLED']) {
  test(`cancellation is unavailable for ${status} invoices`, async ({ page }) => {
    await portal(page, status);
    await expect(page.getByRole('button', { name: 'Anulează factura', exact: true })).toHaveCount(0);
  });
}

for (const status of [409, 503]) {
  test(`failed cancellation requires a reload after ${status}`, async ({ page }) => {
    const requests = await portal(page, 'BLOCKED', status);
    await page.getByRole('button', { name: 'Anulează factura', exact: true }).click();
    await page.getByLabel('Motivul anulării', { exact: true }).fill('Factura duplicata');
    await page.getByRole('button', { name: 'Confirmă anularea', exact: true }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Confirmă anularea', exact: true })).toBeDisabled();
    expect(requests).toHaveLength(1);
  });
}
