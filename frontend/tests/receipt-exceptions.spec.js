import { test, expect } from '@playwright/test';

test('receipt history displays one operation with its reason once and expandable lines', async ({ page }) => {
  await portal(page, 'CONTABILITATE');
  let grouped;
  await page.route('**/api/receipts/2/history?*', (route) => {
    grouped = new URL(route.request().url()).searchParams.get('grouped');
    return route.fulfill({ json: { total: 1, events: [{ id: 10, entity_type: 'receipts', action: 'CONFIRM',
      actor_name: 'Depozit', created_at: '2026-10-21T15:22:09.123456Z', reason: 'Au sosit doar 27 din 50.',
      changes: [{ id: 11, entity_type: 'receipt_items', action: 'UPDATE', line_number: 1, order_number: 'CA-6',
        after: { accepted_quantity: '27.000', rejected_quantity: '0.000', pending_quantity: '0.000', unit: 'BUC' } }] }] } });
  });
  await openPending(page);
  const history = page.getByRole('region', { name: 'Istoric recepție' });
  await expect(history.getByText('recepție confirmată', { exact: true })).toHaveCount(1);
  await expect(history.getByText('Au sosit doar 27 din 50.', { exact: true })).toHaveCount(1);
  await expect(history.locator('.receipt-history-list > li')).toHaveCount(1);
  await history.getByText('Poziții și modificări', { exact: true }).click();
  await expect(history).toContainText('acceptat 27 BUC · respins 0 · în așteptare 0 · CA-6');
  expect(grouped).toBe('1');
});

async function portal(page, role, { covered = false, holdDecision = false } = {}) {
  const user = { id: 1, name: 'Angajat test', role };
  const item = { id: 11, line_number: 1, product_id: null, purchase_order_item_id: null,
    pending_order_item_id: covered ? 101 : null, pending_order_number: covered ? 'CA-1' : null,
    description: 'Marfă de identificat', unit: 'BUC', received_quantity: '10.000', accepted_quantity: '0.000',
    resolved_quantity: '0.000', total_accepted_quantity: '0.000', rejected_quantity: '0.000', pending_quantity: '10.000', acceptances: [] };
  const receipt = { id: 2, number: 'REC-2', supplier_id: 1, supplier_name: 'Furnizor test', delivery_reference: 'AV-1',
    received_at: '2026-10-21T08:00:00Z', status: 'CONFIRMED', version: 2, items: [item] };
  const requests = [];
  let finishDecision;
  await page.context().addCookies([{ name: 'csrf_access_token', value: 'test-csrf', domain: '127.0.0.1', path: '/' }]);
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const body = request.postData() ? request.postDataJSON() : null;
    requests.push({ path, method: request.method(), body, headers: request.headers() });
    if (path === '/api/auth/me') return route.fulfill({ json: { user } });
    if (path.endsWith('/history')) return route.fulfill({ json: { events: [], total: 0 } });
    if (path.endsWith('/clarify')) {
      receipt.version += 1; item.pending_order_item_id = body.purchase_order_item_id; item.pending_order_number = 'CA-1';
      return route.fulfill({ json: { receipt } });
    }
    if (path.endsWith('/resolve') && holdDecision) {
      await new Promise((resolve) => { finishDecision = resolve; });
      receipt.version += 1;
      return route.fulfill({ status: 409, json: { message: 'Recepția a fost modificată. Actualizează datele.' } });
    }
    if (path === '/api/receipts/unordered') return route.fulfill({ status: 201, json: { receipt: { ...receipt, status: 'DRAFT' } } });
    if (path === '/api/receipts/2') return route.fulfill({ json: { receipt } });
    if (path === '/api/purchase-orders/1/delivery') return route.fulfill({ json: { delivery: { items: [
      { id: 101, line_number: 1, product_id: 1, description: 'Produs compatibil', unit: 'BUC', remaining_quantity: '10.000' },
      { id: 102, line_number: 2, product_id: 2, description: 'Unitate diferită', unit: 'KG', remaining_quantity: '10.000' },
      { id: 103, line_number: 3, product_id: 1, description: 'Livrat integral', unit: 'BUC', remaining_quantity: '0.000' },
    ] } } });
    const data = {
      '/api/receipts': { receipts: [receipt], total: 1 }, '/api/receipts/pending': { receipts: [receipt], total: 1 },
      '/api/purchase-orders': { orders: [{ id: 1, number: 'CA-1', supplier_id: 1, status: 'CONFIRMED' },
        { id: 2, number: 'CA-2', supplier_id: 2, status: 'CONFIRMED' }], total: 2 },
      '/api/products': { products: [{ id: 1, sku: 'P1', name: 'Produs compatibil', unit: 'BUC', is_active: true }], total: 1 },
      '/api/suppliers': { suppliers: [{ id: 1, name: 'Furnizor test', is_active: true }], total: 1 },
      '/api/purchase-orders/overdue': { items: [], total: 0 }, '/api/invoices': { invoices: [], total: 0 },
    };
    return route.fulfill({ json: data[path] || {} });
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Privire de ansamblu', exact: true })).toBeVisible();
  return { requests, release: () => finishDecision() };
}

async function openPending(page) {
  await page.getByRole('navigation').getByRole('button', { name: 'Clarificări', exact: true }).click();
  await page.getByRole('button', { name: 'Detalii recepție REC-2', exact: true }).click();
}

test('unordered arrival sends unknown product, exact quantity and CSRF', async ({ page }) => {
  const { requests } = await portal(page, 'DEPOZIT');
  await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
  await page.getByRole('button', { name: 'Fără comandă', exact: true }).click();
  await page.getByLabel('Furnizor', { exact: true }).selectOption('1');
  await page.getByLabel('Document de livrare', { exact: true }).fill('AV-NECOMANDAT');
  await page.getByLabel('Descriere 1', { exact: true }).fill('Marfă nouă');
  await page.getByLabel('Cantitate sosită 1', { exact: true }).fill('2,125');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Salvează ciorna', exact: true }).click();
  await expect(page.getByText('Recepția REC-2 a fost salvată ca ciornă.', { exact: true })).toBeVisible();
  const saved = requests.find((request) => request.path === '/api/receipts/unordered');
  expect(saved.body.items).toEqual([{ product_id: null, description: 'Marfă nouă', unit: 'BUC', received_quantity: '2.125' }]);
  expect(saved.headers['x-csrf-token']).toBe('test-csrf');
  expect(requests.filter((request) => request.method === 'POST')).toHaveLength(1);
});

test('buyers see compatible order positions and cannot make warehouse decisions', async ({ page }) => {
  const { requests } = await portal(page, 'ACHIZITII');
  await openPending(page);
  await expect(page.getByRole('button', { name: 'Acceptă cantitatea', exact: true })).toHaveCount(0);
  await expect(page.getByRole('option', { name: 'CA-2', exact: true })).toHaveCount(0);
  await page.getByLabel('Comandă pentru poziția 1', { exact: true }).selectOption('1');
  await expect(page.getByLabel('Produs comandat 1', { exact: true })).toHaveValue('101');
  await expect(page.getByRole('option', { name: /Unitate diferită|Livrat integral/ })).toHaveCount(0);
  await page.getByLabel('Observații decizie 1', { exact: true }).fill('Acoperire comercială');
  await page.getByRole('button', { name: 'Asociază comanda', exact: true }).click();
  await expect(page.getByText('Comanda a fost asociată. Marfa așteaptă decizia Depozitului.', { exact: true })).toBeVisible();
  expect(requests.find((request) => request.path.endsWith('/clarify')).body).toEqual({
    version: 2, reason: 'Acoperire comercială', purchase_order_item_id: 101,
  });
});

test('warehouse decisions lock the dialog and require reload after a conflict', async ({ page }) => {
  const mock = await portal(page, 'DEPOZIT', { covered: true, holdDecision: true });
  await openPending(page);
  await page.getByLabel('Cantitate de decis 1', { exact: true }).fill('6');
  await page.getByLabel('Observații decizie 1', { exact: true }).fill('Control fizic');
  await page.getByRole('button', { name: 'Acceptă cantitatea', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Închide detaliile', exact: true })).toBeDisabled();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeVisible();
  mock.release();
  await expect(page.getByRole('alert')).toContainText('Recepția a fost modificată.');
  await expect(page.getByRole('button', { name: 'Acceptă cantitatea', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Respinge cantitatea', exact: true })).toBeDisabled();
  expect(mock.requests.filter((request) => request.path.endsWith('/resolve'))).toHaveLength(1);
  await page.getByRole('button', { name: 'Actualizează datele', exact: true }).click();
  await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Versiunea 3');
  await expect(page.getByRole('button', { name: 'Acceptă cantitatea', exact: true })).toBeEnabled();
});

test('accounting can read pending quantities and history without operational buttons', async ({ page }) => {
  await portal(page, 'CONTABILITATE');
  await openPending(page);
  await expect(page.getByRole('region', { name: 'Cantități în așteptare' })).toContainText('nu sunt disponibile pentru facturare');
  await expect(page.getByRole('region', { name: 'Istoric recepție' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Asociază comanda', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Acceptă cantitatea', exact: true })).toHaveCount(0);
});

test('uncertain arrival cannot be retried by switching receipt modes', async ({ page }) => {
  const { requests } = await portal(page, 'DEPOZIT');
  await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
  await page.getByRole('button', { name: 'Fără comandă', exact: true }).click();
  await page.getByLabel('Furnizor', { exact: true }).selectOption('1');
  await page.getByLabel('Document de livrare', { exact: true }).fill('AV-INCERT');
  await page.getByLabel('Descriere 1', { exact: true }).fill('Marfă');
  await page.getByLabel('Cantitate sosită 1', { exact: true }).fill('1');
  await page.route('**/api/receipts/unordered', (route) => route.fulfill({ status: 503, json: { message: 'Rezultat incert' } }));
  await page.getByRole('button', { name: 'Salvează ciorna', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Verifică recepțiile');
  await expect(page.getByRole('button', { name: 'Din comandă', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Fără comandă', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Salvează ciorna', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Vezi recepțiile', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recepții', exact: true, level: 1 })).toBeVisible();
  expect(requests.some((request) => request.path === '/api/receipts' && request.method === 'POST')).toBe(false);
});
