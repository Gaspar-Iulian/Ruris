import { test, expect } from '@playwright/test';

const PDF = Buffer.from('%PDF-1.4\nDocument RURIS\n%%EOF\n');

async function portal(page, { role = 'ACHIZITII', uploadStatus = 201, errorOnList = false } = {}) {
  const requests = [];
  let version = 2;
  let files = [];
  const order = () => ({ id: 1, number: 'CA-DOC', supplier_id: 1, supplier_name: 'Furnizor test', status: 'CONFIRMED', version,
    currency: 'RON', items: [{ id: 11, line_number: 1, product_id: 1, description: 'Produs test', quantity: '5.000', unit: 'BUC' }] });
  const record = { id: 1, original_name: 'factură.pdf', media_type: 'application/pdf', size_bytes: PDF.length,
    status: 'ACTIVE', upload_reason: 'Document justificativ', uploaded_by_name: 'Achiziții', created_at: '2026-10-21T08:00:00Z' };
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    requests.push({ path: url.pathname, method: request.method(), headers: request.headers(), body: request.postData() });
    if (url.pathname === '/api/auth/me') return route.fulfill({ json: { user: { id: 1, name: 'Angajat test', role } } });
    if (url.pathname === '/api/purchase-orders/1') return route.fulfill({ json: { order: order() } });
    if (url.pathname.endsWith('/delivery')) return route.fulfill({ json: { delivery: { ...order(), items: [] } } });
    if (url.pathname === '/api/documents/orders/1/attachments') {
      if (request.method() === 'GET') {
        if (errorOnList) return route.fulfill({ status: 401, json: { message: 'Sesiunea a expirat.' } });
        return route.fulfill({ json: { attachments: files, total: files.length, document_version: version, can_manage: role === 'ACHIZITII', max_attachments: 50 } });
      }
      if (uploadStatus === 409) { version += 1; return route.fulfill({ status: 409, json: { message: 'Document modificat.' } }); }
      version += 1; files = [record];
      if (uploadStatus === 503) return route.fulfill({ status: 503, json: { message: 'Raspuns incert.' } });
      return route.fulfill({ status: 201, json: { attachment: record, document: order(), replayed: false } });
    }
    if (url.pathname.endsWith('/download')) return route.fulfill({ status: 503, json: { message: 'Integritatea fisierului nu a putut fi confirmata.' } });
    const data = { '/api/purchase-orders': { orders: [order()], total: 1 }, '/api/purchase-orders/overdue': { items: [], total: 0 },
      '/api/receipts': { receipts: [], total: 0 }, '/api/receipts/pending': { receipts: [], total: 0 },
      '/api/stock': { stock: [], total: 0 }, '/api/products': { products: [], total: 0 } };
    return route.fulfill({ json: data[url.pathname] || {} });
  });
  await page.context().addCookies([{ name: 'csrf_access_token', value: 'attachment-csrf', url: 'http://127.0.0.1:5173', sameSite: 'Lax' }]);
  await page.goto('/');
  await page.getByRole('navigation').getByRole('button', { name: 'Comenzi', exact: true }).click();
  await page.getByRole('button', { name: 'Detalii comandă CA-DOC', exact: true }).click();
  return { requests };
}

async function openFiles(page) {
  const panel = page.getByRole('region', { name: 'Documente atașate' });
  await panel.getByRole('button', { name: 'Documente', exact: true }).click();
  return panel;
}

async function selectFile(panel, { name = 'factură.pdf', buffer = PDF } = {}) {
  await panel.getByLabel('Fișier', { exact: true }).setInputFiles({ name, mimeType: 'application/pdf', buffer });
  await panel.getByLabel('Observații fișier', { exact: true }).fill('Document justificativ');
}

test('files load on demand and upload uses multipart, CSRF and a stable operation key', async ({ page }) => {
  const mock = await portal(page);
  expect(mock.requests.some((request) => request.path.startsWith('/api/documents/'))).toBe(false);
  const panel = await openFiles(page);
  await selectFile(panel);
  await panel.getByRole('button', { name: 'Încarcă fișierul', exact: true }).click();
  await expect(panel.getByText('factură.pdf', { exact: true })).toBeVisible();
  const sent = mock.requests.find((request) => request.path.endsWith('/attachments') && request.method === 'POST');
  expect(sent.headers['x-csrf-token']).toBe('attachment-csrf');
  expect(sent.headers['content-type']).toMatch(/^multipart\/form-data; boundary=/);
  expect(sent.body).toContain('name="version"\r\n\r\n2');
  expect(sent.body).toMatch(/[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}/);
});

test('unsupported extensions and oversized files are rejected before upload', async ({ page }) => {
  const mock = await portal(page);
  const panel = await openFiles(page);
  await selectFile(panel, { name: 'document.html' });
  await panel.getByRole('button', { name: 'Încarcă fișierul', exact: true }).click();
  await expect(panel.getByRole('alert')).toContainText('PDF, PNG sau JPG');
  await selectFile(panel, { buffer: Buffer.alloc(10 * 1024 * 1024 + 1, 'a') });
  await panel.getByRole('button', { name: 'Încarcă fișierul', exact: true }).click();
  await expect(panel.getByRole('alert')).toContainText('10 MB');
  expect(mock.requests.some((request) => request.method === 'POST')).toBe(false);
});

for (const status of [409, 503]) {
  test(`a ${status} upload result requires a refresh and cannot be blindly repeated`, async ({ page }) => {
    const mock = await portal(page, { uploadStatus: status });
    const panel = await openFiles(page);
    await selectFile(panel);
    await panel.getByRole('button', { name: 'Încarcă fișierul', exact: true }).click();
    await expect(panel.getByRole('button', { name: 'Actualizează documentul', exact: true })).toBeVisible();
    await expect(panel.getByRole('button', { name: 'Încarcă fișierul', exact: true })).toHaveCount(0);
    expect(mock.requests.filter((request) => request.method === 'POST')).toHaveLength(1);
    await panel.getByRole('button', { name: 'Actualizează documentul', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Versiunea 3');
    const refreshed = await openFiles(page);
    if (status === 503) await expect(refreshed.getByText('factură.pdf', { exact: true })).toBeVisible();
  });
}

test('accounting can read order files without upload controls and the warehouse has no file panel', async ({ page }) => {
  await portal(page, { role: 'CONTABILITATE' });
  const panel = await openFiles(page);
  await expect(panel.getByRole('button', { name: 'Încarcă fișierul', exact: true })).toHaveCount(0);
  await page.unrouteAll({ behavior: 'wait' });
  await portal(page, { role: 'DEPOZIT' });
  await expect(page.getByRole('region', { name: 'Documente atașate' })).toHaveCount(0);
});

test('session expiry while loading files removes protected content', async ({ page }) => {
  await portal(page, { errorOnList: true });
  await openFiles(page);
  await expect(page.getByRole('heading', { name: 'Intră în contul tău' })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('a failed download reports the error and leaves the document usable', async ({ page }) => {
  await portal(page);
  const panel = await openFiles(page);
  await selectFile(panel);
  await panel.getByRole('button', { name: 'Încarcă fișierul', exact: true }).click();
  await panel.getByRole('button', { name: 'Descarcă factură.pdf', exact: true }).click();
  await expect(panel.getByRole('alert')).toContainText('Integritatea fisierului');
  await expect(page.getByRole('button', { name: 'Închide detaliile' })).toBeEnabled();
});
