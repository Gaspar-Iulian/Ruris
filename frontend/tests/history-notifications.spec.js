import { test, expect } from '@playwright/test';

async function portal(page, role = 'ACHIZITII') {
  const user = { id: 1, name: 'Angajat test', role };
  const requests = [];
  const order = { id: 1, number: 'CA-1', supplier_id: 1, supplier_name: 'Furnizor test', status: 'CONFIRMED',
    version: 2, delivery_status: 'NOT_RECEIVED', items: [{ id: 11, line_number: 1, description: 'Produs test', quantity: '6.000', unit: 'BUC' }] };
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    requests.push(url.pathname);
    if (url.pathname === '/api/auth/me') return route.fulfill({ json: { user } });
    if (url.pathname === '/api/purchase-orders/1') return route.fulfill({ json: { order } });
    if (url.pathname === '/api/purchase-orders/1/delivery') return route.fulfill({ json: { delivery: { ...order,
      items: [{ ...order.items[0], accepted_quantity: '0.000', remaining_quantity: '6.000', delivery_status: 'NOT_RECEIVED' }] } } });
    if (url.pathname.endsWith('/history')) return route.fulfill({ json: { total: 11, events: [{ id: url.searchParams.get('page') === '2' ? 2 : 1,
      action: 'UPDATE', entity_type: 'purchase_order_items', line_number: 1, actor_name: 'Responsabil achiziții',
      created_at: '2026-10-21T08:00:00Z', reason: role === 'DEPOZIT' ? null : 'Corectare cantitate și preț',
      before: { quantity: '4.000', ...(role === 'DEPOZIT' ? {} : { unit_price: '2.0000' }) },
      after: { quantity: '6.000', ...(role === 'DEPOZIT' ? {} : { unit_price: '3.0000' }) } }] } });
    if (url.pathname === '/api/notifications') {
      const second = url.searchParams.get('page') === '2';
      return route.fulfill({ json: { total: 21, notifications: [{ id: second ? 2 : 1, kind: 'RECEIPT_BUYER',
        subject: second ? 'Rezultat de verificat' : 'Clarificare recepție REC-1', body: '<img src=x onerror=alert(1)>\nMarfă în așteptare: 10.000 BUC',
        as_of: '2026-10-21', transport: 'LOCAL_MAILPIT', status: second ? 'UNKNOWN' : 'SENT', attempt_count: 1,
        created_at: '2026-10-21T08:00:00Z', sent_at: second ? null : '2026-10-21T08:00:01Z',
        last_error: second ? 'WORKER_INTERRUPTED' : null, attempts: [{ number: 1, status: second ? 'UNKNOWN' : 'SENT', started_at: '2026-10-21T08:00:00Z' }] }] } });
    }
    const data = { '/api/purchase-orders': { orders: [order], total: 1 }, '/api/receipts': { receipts: [], total: 0 },
      '/api/products': { products: [], total: 0 }, '/api/purchase-orders/overdue': { items: [], total: 0 },
      '/api/receipts/pending': { receipts: [], total: 0 }, '/api/invoices': { invoices: [], total: 0 },
      '/api/users': { users: [user], total: 1 } };
    return route.fulfill({ json: data[url.pathname] || {} });
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Privire de ansamblu', exact: true })).toBeVisible();
  return { requests };
}

test('order history loads on request and displays changes with pagination', async ({ page }) => {
  const { requests } = await portal(page);
  await page.getByRole('navigation').getByRole('button', { name: 'Comenzi', exact: true }).click();
  await page.getByRole('button', { name: 'Detalii comandă CA-1', exact: true }).click();
  expect(requests.some((path) => path.endsWith('/history'))).toBe(false);
  const history = page.getByRole('region', { name: 'Istoric comandă' });
  await history.getByRole('button', { name: 'Istoric', exact: true }).click();
  await expect(history).toContainText('Responsabil achiziții');
  await history.getByText('Modificări', { exact: true }).click();
  await expect(history).toContainText('4,000 → 6,000');
  await expect(history).toContainText('2,0000 → 3,0000');
  await history.getByRole('button', { name: 'Mai vechi', exact: true }).click();
  await expect(history).toContainText('Pagina 2 din 2');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('warehouse history displays only operational fields returned by the API', async ({ page }) => {
  await portal(page, 'DEPOZIT');
  await page.getByRole('navigation').getByRole('button', { name: 'Comenzi', exact: true }).click();
  await page.getByRole('button', { name: 'Detalii comandă CA-1', exact: true }).click();
  const history = page.getByRole('region', { name: 'Istoric comandă' });
  await history.getByRole('button', { name: 'Istoric', exact: true }).click();
  await history.getByText('Modificări', { exact: true }).click();
  await expect(history).toContainText('Cantitate');
  await expect(history).not.toContainText('Preț unitar');
});

test('history renders arbitrary product descriptions as text', async ({ page }) => {
  await portal(page);
  await page.route('**/api/purchase-orders/1/history?*', (route) => route.fulfill({ json: { total: 1, events: [{
    id: 1, action: 'UPDATE', entity_type: 'purchase_order_items', line_number: 1, actor_name: 'Achiziții',
    created_at: '2026-10-21T08:00:00Z', before: { description: 'Produs' }, after: { description: '__proto__' },
  }] } }));
  await page.getByRole('button', { name: 'Detalii comandă CA-1', exact: true }).click();
  const history = page.getByRole('region', { name: 'Istoric comandă' });
  await history.getByRole('button', { name: 'Istoric', exact: true }).click();
  await history.getByText('Modificări', { exact: true }).click();
  await expect(history).toContainText('Produs → __proto__');
});

test('history can recover from a temporary error', async ({ page }) => {
  await portal(page);
  let failed = false;
  await page.route('**/api/purchase-orders/1/history?*', async (route) => {
    if (!failed) { failed = true; return route.fulfill({ status: 503, json: { message: 'Istoric indisponibil' } }); }
    return route.fallback();
  });
  await page.getByRole('button', { name: 'Detalii comandă CA-1', exact: true }).click();
  await page.getByRole('region', { name: 'Istoric comandă' }).getByRole('button', { name: 'Istoric', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Istoric indisponibil');
  await page.getByRole('button', { name: 'Reîncarcă istoricul', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Istoric comandă' })).toContainText('Responsabil achiziții');
});

for (const role of ['ACHIZITII', 'DEPOZIT', 'CONTABILITATE']) {
  test(`notification journal displays delivery attempts safely for ${role}`, async ({ page }) => {
    await portal(page, role);
    await page.getByRole('navigation').getByRole('button', { name: 'Notificări', exact: true }).click();
    await page.locator('.notification-entry summary').click();
    await expect(page.getByRole('region', { name: 'Jurnal notificări' })).toContainText('Acceptat de server');
    await expect(page.locator('.notification-content pre')).toContainText('<img src=x onerror=alert(1)>');
    await expect(page.locator('.notification-content img')).toHaveCount(0);
    await page.getByRole('button', { name: 'Următor', exact: true }).click();
    await page.locator('.notification-entry summary').click();
    await expect(page.getByRole('region', { name: 'Jurnal notificări' })).toContainText('Procesarea a fost întreruptă');
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('administrator has no access to business notification journal', async ({ page }) => {
  await portal(page, 'ADMIN');
  await expect(page.getByRole('navigation').getByRole('button', { name: 'Notificări', exact: true })).toHaveCount(0);
});

test('session expiry while reading notifications removes protected content', async ({ page }) => {
  await portal(page);
  await page.route('**/api/notifications?*', (route) => route.fulfill({ status: 401, json: { message: 'Sesiune expirată' } }));
  await page.getByRole('navigation').getByRole('button', { name: 'Notificări', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Intră în contul tău', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Jurnal notificări' })).toHaveCount(0);
});
