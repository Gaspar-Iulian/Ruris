import { test, expect } from '@playwright/test';

async function mockApi(page, role = 'ACHIZITII', { emptyCatalog = false, draftOrder = false, draftReceipt = false } = {}) {
  let loggedIn = false;
  let expired = false;
  const user = { id: 1, name: 'Iulian Gaspar', email: 'test@example.com', role };
  const users = [{ ...user, is_active: true }];
  const products = emptyCatalog ? [] : [{ id: 1, sku: 'FLT-001', name: 'Filtru de aer', unit: 'BUC', is_active: true }];
  const suppliers = emptyCatalog ? [] : [{ id: 1, name: 'Furnizor test', is_active: true }];
  const orders = [{ id: 1, number: 'CA-1024', supplier_id: 1, supplier_name: 'Furnizor test', currency: 'RON', status: draftOrder ? 'DRAFT' : 'CONFIRMED', delivery_status: draftOrder ? null : 'PARTIAL', version: draftOrder ? 1 : 2,
    items: [{ id: 1, line_number: 1, product_id: 1, sku: 'FLT-001', description: 'Filtru de aer', quantity: '12.000', unit: 'BUC', ...(role !== 'DEPOZIT' ? { unit_price: '15.0000' } : {}) }] }];
  const receipts = [{ id: 2, number: 'REC-248', supplier_id: 1, version: 1, delivery_reference: 'AV-842', received_at: '2026-10-20T08:00:00Z', status: draftReceipt ? 'DRAFT' : 'CONFIRMED', items: [
    { id: 11, line_number: 1, purchase_order_item_id: 1, product_id: 1, description: 'Filtru de aer', unit: 'BUC', received_quantity: '77.000', accepted_quantity: draftReceipt ? '0.000' : '77.000', rejected_quantity: '0.000', pending_quantity: draftReceipt ? '77.000' : '0.000' },
  ] }];
  let stockQuantity = 24;
  const invoices = [{ id: 3, series: 'RUR', number: '2026-184', supplier_id: 1, invoice_date: '2026-10-20', total_amount: '1200.00', currency: 'RON', status: 'BLOCKED' }];
  const items = [{ id: 4, order_number: 'CA-1024', description: 'Filtru de aer', remaining_quantity: '12.000', unit: 'BUC', expected_date: '2026-10-17', days_overdue: 3 }];
  const requests = [];
  await page.context().addCookies([{ name: 'csrf_access_token', value: 'test-csrf', domain: '127.0.0.1', path: '/' }]);
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    requests.push({ path, method: request.method(), headers: request.headers(), body: request.postData() ? request.postDataJSON() : null });
    if (path === '/api/auth/login') { loggedIn = true; return route.fulfill({ json: { user } }); }
    if (path === '/api/auth/logout') { loggedIn = false; return route.fulfill({ json: { message: 'OK' } }); }
    if (!loggedIn || expired) return route.fulfill({ status: 401, json: { message: 'Sesiune expirată' } });
    if (path === '/api/invoices' && request.method() === 'POST') {
      const body = request.postDataJSON();
      const invoice = { id: 4, ...body, status: 'DRAFT', version: 1, net_amount: '25.31', vat_amount: '4.81', total_amount: '30.12' };
      invoices.push(invoice);
      return route.fulfill({ status: 201, json: { message: 'Ciorna facturii a fost creata.', invoice } });
    }
    if (path === '/api/receipts/2') return route.fulfill({ json: { receipt: receipts[0] } });
    if (path === '/api/receipts/2/confirm' && request.method() === 'POST') {
      const receipt = receipts[0];
      const body = request.postDataJSON();
      if (role !== 'DEPOZIT') return route.fulfill({ status: 403, json: { message: 'Acces refuzat.' } });
      if (receipt.status !== 'DRAFT' || receipt.version !== body.version) return route.fulfill({ status: 409, json: { message: 'Recepția a fost modificată.' } });
      for (const line of receipt.items) {
        const classified = body.items.find((item) => item.id === line.id);
        Object.assign(line, classified);
        stockQuantity += Number(classified.accepted_quantity);
      }
      receipt.status = 'CONFIRMED'; receipt.version += 1;
      return route.fulfill({ json: { message: 'Receptia a fost confirmata.', receipt } });
    }
    if (request.method() === 'POST' && ['/api/products', '/api/suppliers'].includes(path)) {
      const supplier = path === '/api/suppliers';
      const records = supplier ? suppliers : products;
      const record = { id: records.length + 1, ...request.postDataJSON(), is_active: true };
      records.push(record);
      return route.fulfill({ status: 201, json: { [supplier ? 'supplier' : 'product']: record } });
    }
    if (path === '/api/users' && request.method() === 'POST') {
      const body = request.postDataJSON();
      const created = { id: users.length + 1, name: body.name, email: body.email, role: body.role, is_active: true };
      users.push(created);
      return route.fulfill({ status: 201, json: { user: created } });
    }
    if (path === '/api/purchase-orders' && request.method() === 'POST') {
      const body = request.postDataJSON();
      const order = { id: 2, number: 'CA-1025', ...body, supplier_name: suppliers.find((supplier) => supplier.id === body.supplier_id)?.name,
        items: body.items.map((line, index) => ({ ...line, id: index + 10, line_number: index + 1, sku: products.find((product) => product.id === line.product_id)?.sku,
          description: products.find((product) => product.id === line.product_id)?.name, unit: products.find((product) => product.id === line.product_id)?.unit })), status: 'DRAFT', version: 1 };
      orders.push(order);
      return route.fulfill({ status: 201, json: { order } });
    }
    if (path === '/api/receipts' && request.method() === 'POST') {
      const body = request.postDataJSON();
      const receipt = { id: 3, number: 'REC-249', ...body, status: 'DRAFT', version: 1 };
      receipts.push(receipt);
      return route.fulfill({ status: 201, json: { receipt } });
    }
    if (path === '/api/purchase-orders/1/delivery') return route.fulfill({ json: { delivery: {
      id: 1, number: 'CA-1024', status: orders[0].status, delivery_status: orders[0].delivery_status,
      items: [{ id: 1, line_number: 1, product_id: 1, description: 'Filtru de aer', quantity: '100.000', accepted_quantity: '40.000', remaining_quantity: '60.000', delivery_status: 'PARTIAL', unit: 'BUC' },
        { id: 2, line_number: 2, product_id: 1, description: 'Filtru de aer suplimentar', quantity: '20.000', accepted_quantity: '0.000', remaining_quantity: '20.000', delivery_status: 'NOT_RECEIVED', unit: 'BUC' }],
    } } });
    if (path === '/api/auth/me') return route.fulfill({ json: { user } });
    if (path === '/api/purchase-orders/1/invoicing') return route.fulfill({ json: { order: {
      ...orders[0], items: [{ id: 1, product_id: 1, description: 'Filtru de aer', unit: 'BUC', quantity: '100.000', unit_price: '2.0000', vat_rate: '19.00', accepted_quantity: '77.000', allocated_quantity: '20.000', available_quantity: '57.000' }],
    } } });
    if (path === '/api/purchase-orders/1/confirm' && request.method() === 'POST') {
      const order = orders[0];
      if (role !== 'ACHIZITII') return route.fulfill({ status: 403, json: { message: 'Acces refuzat.' } });
      if (order.status !== 'DRAFT' || request.postDataJSON().version !== order.version) return route.fulfill({ status: 409, json: { message: 'Comanda a fost modificată.' } });
      order.status = 'CONFIRMED'; order.version += 1;
      return route.fulfill({ json: { order: { ...order, items: [{ id: 1, description: 'Filtru de aer', quantity: '12.000', unit: 'BUC' }] } } });
    }
    if (path === '/api/purchase-orders/1') return route.fulfill({ json: { order: { ...orders[0], items: [{ id: 1, description: 'Filtru de aer', quantity: '12.000', unit: 'BUC' }] } } });
    if (path === '/api/purchase-orders/overdue') return route.fulfill({ json: { items, total: 1 } });
    const data = {
      '/api/purchase-orders': { orders, total: orders.length },
      '/api/receipts': { receipts, total: receipts.length },
      '/api/invoices': { invoices, total: invoices.length },
      '/api/products': { products, total: products.length },
      '/api/suppliers': { suppliers, total: suppliers.length },
      '/api/stock': { stock: [{ id: 1, sku: 'FLT-001', name: 'Filtru de aer', unit: 'BUC', quantity: stockQuantity.toFixed(3) }], total: 1 },
      '/api/users': { users, total: users.length },
    };
    return route.fulfill({ json: data[path] || {} });
  });
  return { requests, orders, receipts, expire: () => { expired = true; } };
}

async function login(page) {
  await page.goto('/');
  await page.getByLabel('Adresă de email').fill('test@example.com');
  await page.getByLabel('Parolă', { exact: true }).fill('test-password');
  await page.getByRole('button', { name: 'Autentificare', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Privire de ansamblu' })).toBeVisible();
}

for (const role of ['ADMIN', 'ACHIZITII', 'DEPOZIT', 'CONTABILITATE']) {
  test(`login and navigation for ${role}`, async ({ page }) => {
    const { requests } = await mockApi(page, role);
    await login(page);
    const menu = page.getByRole('navigation', { name: 'Navigare principală' });
    if (role === 'ADMIN') {
      await expect(menu.getByRole('button', { name: 'Utilizatori', exact: true })).toBeVisible();
      await expect(menu.getByRole('button', { name: 'Comenzi', exact: true })).toHaveCount(0);
      expect(requests.some((request) => request.path === '/api/purchase-orders/overdue')).toBe(false);
    } else {
      await expect(menu.getByRole('button', { name: 'Stoc', exact: true })).toBeVisible();
      await expect(menu.getByRole('button', { name: 'Facturi', exact: true })).toHaveCount(role === 'CONTABILITATE' ? 1 : 0);
      await expect(menu.getByRole('button', { name: 'Utilizatori', exact: true })).toHaveCount(0);
    }
  });
}

test('logout sends CSRF and removes workspace', async ({ page }) => {
  const { requests } = await mockApi(page);
  await login(page);
  await page.getByRole('button', { name: 'Deconectare', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Intră în contul tău' })).toBeVisible();
  expect(requests.find((request) => request.path === '/api/auth/logout').headers['x-csrf-token']).toBe('test-csrf');
});

test('expired session removes protected data', async ({ page }) => {
  const mock = await mockApi(page);
  await login(page);
  await expect(page.getByText('CA-1024').first()).toBeVisible();
  mock.expire();
  await page.getByRole('button', { name: 'Actualizează' }).click();
  await expect(page.getByRole('heading', { name: 'Intră în contul tău' })).toBeVisible();
  await expect(page.getByText('CA-1024')).toHaveCount(0);
});

test('documents, details, page search and responsive menu', async ({ page }) => {
  await mockApi(page);
  await login(page);
  await page.getByRole('navigation').getByRole('button', { name: 'Comenzi', exact: true }).click();
  await page.getByRole('button', { name: 'Detalii comandă CA-1024' }).click();
  await expect(page.getByRole('dialog')).toContainText('Filtru de aer');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('textbox', { name: 'Caută pe pagina curentă' }).fill('nu exista');
  await expect(page.getByText('Niciun rezultat pe această pagină. Încearcă alt termen.')).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Deschide meniul' }).click();
  await page.getByRole('navigation').getByRole('button', { name: 'Stoc', exact: true }).click();
  await expect(page.getByRole('cell', { name: '24,000' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('visual previews', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Intră în contul tău' })).toBeVisible();
  await page.screenshot({ path: 'test-results/login.png', fullPage: true });
  await login(page);
  await expect(page.getByText('CA-1024').first()).toBeVisible();
  await page.screenshot({ path: 'test-results/dashboard.png', fullPage: true });
});

test('invalid credentials remain on login with a clear error', async ({ page }) => {
  await mockApi(page);
  await page.route('**/api/auth/login', (route) => route.fulfill({ status: 401, json: { message: 'Emailul sau parola sunt incorecte.' } }));
  await page.goto('/');
  await page.getByLabel('Adresă de email').fill('test@example.com');
  await page.getByLabel('Parolă', { exact: true }).fill('wrong-password');
  await page.getByRole('button', { name: 'Autentificare', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Emailul sau parola sunt incorecte.');
  await expect(page.getByRole('navigation')).toHaveCount(0);
});

async function fillOrder(page) {
  await page.getByRole('button', { name: 'Comandă nouă', exact: true }).click();
  await page.getByLabel('Furnizor', { exact: true }).selectOption('1');
  await page.getByLabel('Produs 1', { exact: true }).selectOption('1');
  await page.getByLabel('Cantitate 1', { exact: true }).fill('2,5');
  await page.getByLabel('Preț unitar 1', { exact: true }).fill('10,1250');
  await page.getByLabel('TVA (%) 1', { exact: true }).fill('19');
  await page.getByLabel('Termen 1', { exact: true }).fill('2026-11-15');
}

test('general portal copy and order creation send exact decimals and CSRF', async ({ page }) => {
  const { requests } = await mockApi(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Portal Intern RURIS' })).toBeVisible();
  await expect(page.getByText('TREI ECHIPE. UN SINGUR FLUX.')).toHaveCount(0);
  await login(page);
  await fillOrder(page);
  await page.getByLabel('Monedă', { exact: true }).selectOption('EUR');
  await page.screenshot({ path: 'test-results/order-form.png', fullPage: true });
  await page.getByRole('button', { name: 'Salvează ciorna' }).click();
  await expect(page.getByText('Comanda CA-1025 a fost salvată ca ciornă.')).toBeVisible();
  const posts = requests.filter((request) => request.path === '/api/purchase-orders' && request.method === 'POST');
  expect(posts).toHaveLength(1);
  expect(posts[0].headers['x-csrf-token']).toBe('test-csrf');
  expect(posts[0].body).toEqual({ supplier_id: 1, currency: 'EUR', items: [{ product_id: 1, quantity: '2.5', unit_price: '10.1250', vat_rate: '19', expected_date: '2026-11-15' }] });
  await expect(page.getByRole('cell', { name: 'CA-1025', exact: true })).toBeVisible();
});

test('order rows can be added and removed and invalid quantity is not submitted', async ({ page }) => {
  const { requests } = await mockApi(page);
  await login(page);
  await fillOrder(page);
  await page.getByRole('button', { name: 'Adaugă produs' }).click();
  await expect(page.getByLabel('Produs 2', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Elimină poziția 2' }).click();
  await expect(page.getByLabel('Produs 2', { exact: true })).toHaveCount(0);
  await page.getByLabel('Cantitate 1', { exact: true }).fill('0');
  await page.getByRole('button', { name: 'Salvează ciorna' }).click();
  await expect(page.getByRole('alert')).toContainText('cantitate pozitivă');
  expect(requests.some((request) => request.path === '/api/purchase-orders' && request.method === 'POST')).toBe(false);
});

test('server validation preserves the order and other roles cannot create it', async ({ page }) => {
  await mockApi(page);
  await page.route('**/api/purchase-orders', (route) => route.request().method() === 'POST'
    ? route.fulfill({ status: 400, json: { message: 'Furnizorul nu mai este activ.' } }) : route.fallback());
  await login(page);
  await fillOrder(page);
  await page.getByRole('button', { name: 'Salvează ciorna' }).click();
  await expect(page.getByRole('alert')).toContainText('Furnizorul nu mai este activ.');
  await expect(page.getByLabel('Cantitate 1', { exact: true })).toHaveValue('2,5');
  await page.getByRole('button', { name: 'Anulează', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Comenzi', exact: true }).first()).toBeVisible();
});

test('catalog excludes inactive entries and loads subsequent pages', async ({ page }) => {
  await mockApi(page);
  await page.route('**/api/products?*', (route) => {
    const params = new URL(route.request().url()).searchParams;
    if (params.get('per_page') !== '100') return route.fallback();
    const products = params.get('page') === '2'
      ? [{ id: 2, sku: 'ACT-002', name: 'Produs activ', unit: 'BUC', is_active: true }]
      : [{ id: 1, sku: 'OLD-001', name: 'Produs inactiv', unit: 'BUC', is_active: false }];
    return route.fulfill({ json: { products, total: 2 } });
  });
  await login(page);
  await page.getByRole('button', { name: 'Comandă nouă', exact: true }).click();
  await expect(page.getByLabel('Produs 1', { exact: true }).getByRole('option', { name: /Produs activ/ })).toHaveCount(1);
  await expect(page.getByLabel('Produs 1', { exact: true }).getByRole('option', { name: /Produs inactiv/ })).toHaveCount(0);
});

for (const role of ['ADMIN', 'DEPOZIT', 'CONTABILITATE']) {
  test(`order creation is hidden for ${role}`, async ({ page }) => {
    await mockApi(page, role);
    await login(page);
    await expect(page.getByRole('button', { name: 'Comandă nouă', exact: true })).toHaveCount(0);
  });
}

test('order form fits mobile and has a clear empty catalog state', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.route('**/api/suppliers?*', (route) => route.fulfill({ json: { suppliers: [], total: 0 } }));
  await login(page);
  await page.getByRole('button', { name: 'Comandă nouă', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Adaugă întâi un furnizor activ');
  await expect(page.getByRole('button', { name: 'Salvează ciorna' })).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('uncertain save cannot be blindly repeated', async ({ page }) => {
  await mockApi(page);
  let submits = 0;
  await page.route('**/api/purchase-orders', (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    submits += 1;
    return route.abort('failed');
  });
  await login(page);
  await fillOrder(page);
  await page.getByRole('button', { name: 'Salvează ciorna' }).click();
  await expect(page.getByRole('alert')).toContainText('Salvarea nu a putut fi confirmată.');
  await expect(page.getByRole('button', { name: 'Salvează ciorna' })).toBeDisabled();
  expect(submits).toBe(1);
  await expect(page.getByRole('button', { name: 'Vezi comenzile', exact: true })).toBeVisible();
});

async function fillUser(page, role = 'ACHIZITII') {
  await page.getByRole('navigation').getByRole('button', { name: 'Utilizatori', exact: true }).click();
  await page.getByRole('button', { name: 'Utilizator nou', exact: true }).click();
  await page.getByLabel('Nume', { exact: true }).fill('Angajat Test');
  await page.getByLabel('Email', { exact: true }).fill('angajat@example.com');
  await page.getByLabel('Rol', { exact: true }).selectOption(role);
  await page.getByLabel('Parolă', { exact: true }).fill('Parola-test-123!');
  await page.getByLabel('Confirmă parola', { exact: true }).fill('Parola-test-123!');
}

for (const role of ['ACHIZITII', 'DEPOZIT', 'CONTABILITATE']) {
  test(`new user creation for ${role}`, async ({ page }) => {
    const { requests } = await mockApi(page, 'ADMIN');
    await login(page);
    await fillUser(page, role);
    await expect(page.getByLabel('Rol', { exact: true }).getByRole('option', { name: 'Administrare', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Creează contul' }).click();
    await expect(page.getByText('Utilizatorul Angajat Test a fost creat.')).toBeVisible();
    await expect(page.getByRole('cell', { name: 'angajat@example.com', exact: true })).toBeVisible();
    const request = requests.find((item) => item.path === '/api/users' && item.method === 'POST');
    expect(request.body).toEqual({ name: 'Angajat Test', email: 'angajat@example.com', password: 'Parola-test-123!', role });
    expect(request.headers['x-csrf-token']).toBe('test-csrf');
    await expect(page.getByLabel('Parolă', { exact: true })).toHaveCount(0);
  });
}

test('new user password rules and mismatch prevent submission', async ({ page }) => {
  const { requests } = await mockApi(page, 'ADMIN');
  await login(page);
  await fillUser(page);
  await page.getByLabel('Parolă', { exact: true }).fill('scurta');
  await page.getByRole('button', { name: 'Creează contul' }).click();
  await expect(page.getByRole('alert')).toContainText('minimum 12 caractere');
  await page.getByLabel('Parolă', { exact: true }).fill('😀'.repeat(20));
  await page.getByRole('button', { name: 'Creează contul' }).click();
  await expect(page.getByRole('alert')).toContainText('maximum 72 de octeți');
  await page.getByLabel('Parolă', { exact: true }).fill('Parola-test-123!');
  await page.getByLabel('Confirmă parola', { exact: true }).fill('Parola-diferita-123!');
  await page.getByRole('button', { name: 'Creează contul' }).click();
  await expect(page.getByRole('alert')).toContainText('Parolele nu coincid.');
  expect(requests.some((item) => item.path === '/api/users' && item.method === 'POST')).toBe(false);
});

test('new user duplicate email preserves form and can be cancelled', async ({ page }) => {
  await mockApi(page, 'ADMIN');
  await page.route('**/api/users', (route) => route.request().method() === 'POST'
    ? route.fulfill({ status: 409, json: { message: 'Emailul este deja folosit de un cont.' } }) : route.fallback());
  await login(page);
  await fillUser(page);
  await page.getByRole('button', { name: 'Creează contul' }).click();
  await expect(page.getByRole('alert')).toContainText('Emailul este deja folosit');
  await expect(page.getByLabel('Nume', { exact: true })).toHaveValue('Angajat Test');
  await page.getByRole('button', { name: 'Anulează', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Utilizator nou', exact: true })).toBeVisible();
});

for (const role of ['ACHIZITII', 'DEPOZIT', 'CONTABILITATE']) {
  test(`new user action is hidden for ${role}`, async ({ page }) => {
    await mockApi(page, role);
    await login(page);
    await expect(page.getByRole('button', { name: 'Utilizator nou', exact: true })).toHaveCount(0);
  });
}

test('new user uncertain result blocks retries and mobile layout fits', async ({ page }) => {
  await mockApi(page, 'ADMIN');
  await login(page);
  await fillUser(page);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.route('**/api/users', (route) => route.request().method() === 'POST' ? route.abort('failed') : route.fallback());
  await page.getByRole('button', { name: 'Creează contul' }).click();
  await expect(page.getByRole('alert')).toContainText('Crearea contului nu a putut fi confirmată.');
  await expect(page.getByRole('button', { name: 'Creează contul' })).toBeDisabled();
  await expect(page.getByLabel('Parolă', { exact: true })).toHaveValue('');
});

async function openCatalogForm(page, kind) {
  await page.getByRole('navigation').getByRole('button', { name: kind === 'supplier' ? 'Furnizori' : 'Produse', exact: true }).click();
  await page.getByRole('button', { name: kind === 'supplier' ? 'Furnizor nou' : 'Produs nou', exact: true }).click();
  await page.getByLabel('Denumire', { exact: true }).fill(kind === 'supplier' ? 'Furnizor nou test' : 'Motor test');
  if (kind === 'supplier') await page.getByLabel('Cod fiscal', { exact: true }).fill('RO12345678');
  else await page.getByLabel('Cod produs', { exact: true }).fill('motor-01');
}

test('empty catalog can be populated and used to create an order', async ({ page }) => {
  const { requests } = await mockApi(page, 'ACHIZITII', { emptyCatalog: true });
  await login(page);
  await openCatalogForm(page, 'supplier');
  await page.getByRole('button', { name: 'Salvează', exact: true }).click();
  await expect(page.getByText('Furnizorul Furnizor nou test a fost salvat.')).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Furnizor nou test', exact: true })).toBeVisible();
  await openCatalogForm(page, 'product');
  await page.getByRole('button', { name: 'Salvează', exact: true }).click();
  await expect(page.getByText('Produsul Motor test a fost salvat.')).toBeVisible();
  await expect(page.getByRole('cell', { name: 'MOTOR-01', exact: true })).toBeVisible();
  const supplierRequest = requests.find((request) => request.path === '/api/suppliers' && request.method === 'POST');
  const productRequest = requests.find((request) => request.path === '/api/products' && request.method === 'POST');
  expect(supplierRequest.body).toEqual({ name: 'Furnizor nou test', tax_country: 'RO', tax_id: 'RO12345678', email: null });
  expect(productRequest.body).toEqual({ name: 'Motor test', sku: 'MOTOR-01', unit: 'BUC' });
  expect(supplierRequest.headers['x-csrf-token']).toBe('test-csrf');
  expect(productRequest.headers['x-csrf-token']).toBe('test-csrf');
  await page.getByRole('navigation').getByRole('button', { name: 'Comenzi', exact: true }).click();
  await fillOrder(page);
  await expect(page.getByLabel('Furnizor', { exact: true }).getByRole('option', { name: 'Furnizor nou test', exact: true })).toHaveCount(1);
  await expect(page.getByLabel('Produs 1', { exact: true }).getByRole('option', { name: /Motor test/ })).toHaveCount(1);
  await page.getByRole('button', { name: 'Salvează ciorna' }).click();
  await expect(page.getByText('Comanda CA-1025 a fost salvată ca ciornă.')).toBeVisible();
});

for (const kind of ['supplier', 'product']) {
  test(`duplicate ${kind} preserves entered data`, async ({ page }) => {
    await mockApi(page);
    await page.route(`**/api/${kind === 'supplier' ? 'suppliers' : 'products'}`, (route) => route.request().method() === 'POST'
      ? route.fulfill({ status: 409, json: { message: 'Înregistrarea există deja.' } }) : route.fallback());
    await login(page);
    await openCatalogForm(page, kind);
    await page.getByRole('button', { name: 'Salvează', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Înregistrarea există deja.');
    await expect(page.getByLabel('Denumire', { exact: true })).toHaveValue(kind === 'supplier' ? 'Furnizor nou test' : 'Motor test');
    await page.getByRole('button', { name: 'Anulează', exact: true }).click();
    await expect(page.getByRole('button', { name: kind === 'supplier' ? 'Furnizor nou' : 'Produs nou', exact: true })).toBeVisible();
  });
}

for (const role of ['ADMIN', 'DEPOZIT', 'CONTABILITATE']) {
  test(`catalog creation is hidden for ${role}`, async ({ page }) => {
    await mockApi(page, role);
    await login(page);
    if (role !== 'ADMIN') {
      await page.getByRole('navigation').getByRole('button', { name: 'Produse', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Produs nou', exact: true })).toHaveCount(0);
      await page.getByRole('navigation').getByRole('button', { name: 'Furnizori', exact: true }).click();
    }
    await expect(page.getByRole('button', { name: 'Furnizor nou', exact: true })).toHaveCount(0);
  });
}

test('invalid product code is rejected before submission', async ({ page }) => {
  const { requests } = await mockApi(page);
  await login(page);
  await openCatalogForm(page, 'product');
  await page.getByLabel('Cod produs', { exact: true }).fill('cod cu spatii');
  await page.getByRole('button', { name: 'Salvează', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('fără spații');
  expect(requests.some((request) => request.path === '/api/products' && request.method === 'POST')).toBe(false);
});

test('catalog form fits mobile and blocks uncertain retries', async ({ page }) => {
  await mockApi(page);
  await login(page);
  await openCatalogForm(page, 'supplier');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.route('**/api/suppliers', (route) => route.request().method() === 'POST' ? route.abort('failed') : route.fallback());
  await page.getByRole('button', { name: 'Salvează', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Salvarea nu a putut fi confirmată.');
  await expect(page.getByRole('button', { name: 'Salvează', exact: true })).toBeDisabled();
});

test.describe('receipt creation', () => {
  test.use({ timezoneId: 'Europe/Bucharest' });

  async function fillReceipt(page) {
    await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
    await page.getByLabel('Comandă', { exact: true }).selectOption('1');
    await page.getByLabel('Document de livrare', { exact: true }).fill(' AV-900 ');
    await page.getByLabel('Data și ora recepției', { exact: true }).fill('2026-10-21T10:30');
    await page.getByLabel('Cantitate sosită 1', { exact: true }).fill('12,500');
  }

  test('saves a partial draft with exact quantities, UTC and CSRF without changing stock', async ({ page }) => {
    const { requests } = await mockApi(page, 'DEPOZIT');
    await login(page);
    await fillReceipt(page);
    await expect(page.getByText('Rest de livrat:', { exact: false })).toHaveCount(2);
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByText('Recepția REC-249 a fost salvată ca ciornă.')).toBeVisible();
    await expect(page.getByRole('row').filter({ hasText: 'REC-249' })).toContainText('Ciornă');
    const sent = requests.filter((request) => request.path === '/api/receipts' && request.method === 'POST');
    expect(sent).toHaveLength(1);
    expect(sent[0].headers['x-csrf-token']).toBe('test-csrf');
    expect(sent[0].body).toEqual({ purchase_order_id: 1, delivery_reference: 'AV-900', received_at: '2026-10-21T07:30:00.000Z', items: [{ purchase_order_item_id: 1, received_quantity: '12.500' }] });
    expect(requests.filter((request) => request.method === 'POST').map((request) => request.path)).toEqual(['/api/auth/login', '/api/receipts']);
  });

  test('allows recording a surplus and several received lines', async ({ page }) => {
    const { requests } = await mockApi(page, 'DEPOZIT');
    await login(page);
    await page.getByRole('navigation').getByRole('button', { name: 'Recepții', exact: true }).click();
    await fillReceipt(page);
    await page.getByLabel('Cantitate sosită 1', { exact: true }).fill('110');
    await page.getByLabel('Cantitate sosită 2', { exact: true }).fill('2');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByText('Recepția REC-249 a fost salvată ca ciornă.')).toBeVisible();
    expect(requests.find((request) => request.path === '/api/receipts' && request.method === 'POST').body.items).toEqual([
      { purchase_order_item_id: 1, received_quantity: '110' }, { purchase_order_item_id: 2, received_quantity: '2' },
    ]);
  });

  test('rejects invalid and empty quantities before submission', async ({ page }) => {
    const { requests } = await mockApi(page, 'DEPOZIT');
    await login(page);
    await fillReceipt(page);
    for (const value of ['0', '-1', '1.1234', '1000000000000000']) {
      await page.getByLabel('Cantitate sosită 1', { exact: true }).fill(value);
      await page.getByRole('button', { name: 'Salvează ciorna' }).click();
      await expect(page.getByRole('alert')).toContainText('cantitate pozitivă');
    }
    await page.getByLabel('Cantitate sosită 1', { exact: true }).fill('');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByRole('alert')).toContainText('cel puțin un produs');
    expect(requests.some((request) => request.path === '/api/receipts' && request.method === 'POST')).toBe(false);
  });

  test('loads all order pages and excludes drafts and closed orders', async ({ page }) => {
    await mockApi(page, 'DEPOZIT');
    await page.route('**/api/purchase-orders?*', (route) => {
      const params = new URL(route.request().url()).searchParams;
      if (params.get('per_page') !== '100') return route.fallback();
      return route.fulfill({ json: { orders: params.get('page') === '1'
        ? [{ id: 1, number: 'CA-1024', status: 'DRAFT' }, { id: 3, number: 'CA-1026', status: 'CLOSED' }]
        : [{ id: 2, number: 'CA-1025', status: 'CONFIRMED' }], total: 3 } });
    });
    await login(page);
    await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
    const select = page.getByLabel('Comandă', { exact: true });
    await expect(select.getByRole('option', { name: 'CA-1025' })).toHaveCount(1);
    await expect(select.getByRole('option', { name: 'CA-1024' })).toHaveCount(0);
    await expect(select.getByRole('option', { name: 'CA-1026' })).toHaveCount(0);
  });

  test('shows an empty state when no confirmed orders exist', async ({ page }) => {
    await mockApi(page, 'DEPOZIT', { draftOrder: true });
    await login(page);
    await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
    await expect(page.getByText('Nu există comenzi confirmate și deschise.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Salvează ciorna' })).toBeDisabled();
  });

  test('preserves data after server rejection and allows cancellation', async ({ page }) => {
    await mockApi(page, 'DEPOZIT');
    await page.route('**/api/receipts', (route) => route.request().method() === 'POST'
      ? route.fulfill({ status: 409, json: { message: 'Comanda nu mai este deschisă.' } }) : route.fallback());
    await login(page);
    await fillReceipt(page);
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByRole('alert')).toContainText('Comanda nu mai este deschisă.');
    await expect(page.getByLabel('Cantitate sosită 1', { exact: true })).toHaveValue('12,500');
    await page.getByRole('button', { name: 'Anulează', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Recepții', exact: true }).first()).toBeVisible();
  });

  test('clears quantities when the selected order changes', async ({ page }) => {
    const { orders, requests } = await mockApi(page, 'DEPOZIT');
    orders.push({ id: 2, number: 'CA-1025', status: 'CONFIRMED' });
    await page.route('**/api/purchase-orders/2/delivery', (route) => route.fulfill({ json: { delivery: { id: 2, status: 'CONFIRMED', items: [{ id: 99, line_number: 1, description: 'Motor', quantity: '5.000', remaining_quantity: '5.000', unit: 'BUC' }] } } }));
    await login(page);
    await fillReceipt(page);
    await page.getByLabel('Comandă', { exact: true }).selectOption('2');
    await expect(page.getByText('1. Motor', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Cantitate sosită 1', { exact: true })).toHaveValue('');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByRole('alert')).toContainText('cel puțin un produs');
    expect(requests.some((request) => request.path === '/api/receipts' && request.method === 'POST')).toBe(false);
  });

  test('shows source errors and retries loading the products', async ({ page }) => {
    await mockApi(page, 'DEPOZIT');
    let fail = true;
    await page.route('**/api/purchase-orders/1/delivery', (route) => fail ? route.fulfill({ status: 503, json: { message: 'Date indisponibile.' } }) : route.fallback());
    await login(page);
    await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
    await page.getByLabel('Comandă', { exact: true }).selectOption('1');
    await expect(page.getByRole('alert')).toContainText('Date indisponibile.');
    await expect(page.getByRole('button', { name: 'Salvează ciorna' })).toBeDisabled();
    fail = false;
    await page.getByRole('button', { name: 'Reîncarcă produsele' }).click();
    await expect(page.getByLabel('Cantitate sosită 1', { exact: true })).toBeVisible();
  });

  test('blocks a genuinely closed order returned inside delivery', async ({ page }) => {
    await mockApi(page, 'DEPOZIT');
    await page.route('**/api/purchase-orders/1/delivery', (route) => route.fulfill({ json: {
      delivery: { id: 1, number: 'CA-1024', status: 'CLOSED', items: [] },
    } }));
    await login(page);
    await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
    await page.getByLabel('Comandă', { exact: true }).selectOption('1');
    await expect(page.getByRole('alert')).toContainText('Comanda nu mai este deschisă pentru recepție.');
    await expect(page.getByRole('button', { name: 'Salvează ciorna' })).toBeDisabled();
  });

  test('blocks duplicate saves after an uncertain result and fits mobile', async ({ page }) => {
    await mockApi(page, 'DEPOZIT');
    await login(page);
    await fillReceipt(page);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.route('**/api/receipts', (route) => route.request().method() === 'POST' ? route.abort('failed') : route.fallback());
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByRole('alert')).toContainText('Salvarea nu a putut fi confirmată.');
    await expect(page.getByRole('button', { name: 'Salvează ciorna' })).toBeDisabled();
    await page.getByRole('button', { name: 'Vezi recepțiile' }).click();
    await expect(page.getByRole('button', { name: 'Recepție nouă', exact: true })).toBeVisible();
  });

  test('returns to login when the session expires on save', async ({ page }) => {
    const mock = await mockApi(page, 'DEPOZIT');
    await login(page);
    await fillReceipt(page);
    mock.expire();
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByRole('heading', { name: 'Intră în contul tău' })).toBeVisible();
  });

  for (const role of ['ADMIN', 'ACHIZITII', 'CONTABILITATE']) {
    test(`hides receipt creation from ${role}`, async ({ page }) => {
      await mockApi(page, role);
      await login(page);
      await expect(page.getByRole('button', { name: 'Recepție nouă', exact: true })).toHaveCount(0);
      if (role !== 'ADMIN') {
        await page.getByRole('navigation').getByRole('button', { name: 'Recepții', exact: true }).click();
        await expect(page.getByRole('button', { name: 'Recepție nouă', exact: true })).toHaveCount(0);
      }
    });
  }
});

test.describe('invoice creation', () => {
  test('starts from an order and persists its source while allowing invoice differences', async ({ page }) => {
    const mock = await mockApi(page, 'CONTABILITATE');
    await login(page);
    await page.getByRole('button', { name: 'Factură nouă', exact: true }).click();
    await expect(page.getByLabel('Pornire factură', { exact: true })).toHaveValue('order');
    await expect(page.getByRole('button', { name: 'Salvează ciorna' })).toBeDisabled();
    await page.getByLabel('Comandă', { exact: true }).selectOption('1');
    await expect(page.getByLabel('Furnizor', { exact: true })).toHaveValue('1');
    await expect(page.getByLabel('Furnizor', { exact: true })).toBeDisabled();
    await expect(page.getByLabel('Produs 1', { exact: true })).toHaveValue('1');
    await expect(page.getByLabel('Cantitate 1', { exact: true })).toHaveValue('100.000');
    await expect(page.getByLabel('Preț unitar 1', { exact: true })).toHaveValue('2.0000');
    await expect(page.getByLabel('TVA (%) 1', { exact: true })).toHaveValue('19.00');
    await expect(page.getByText(/Comandat: 100,000 BUC.*Acceptat: 77,000.*Asociat facturilor: 20,000.*Disponibil de asociat: 57,000/)).toBeVisible();
    await page.getByLabel('Preț unitar 1', { exact: true }).fill('3,0000');
    await page.getByLabel('Monedă', { exact: true }).selectOption('EUR');
    await page.getByLabel('Număr factură', { exact: true }).fill('ORD-01');
    await page.getByLabel('Data facturii', { exact: true }).fill('2026-10-21');
    await page.getByLabel('Scadență', { exact: true }).fill('2026-11-21');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByText('Factura ORD-01 a fost salvată ca ciornă.')).toBeVisible();
    const sent = mock.requests.find((request) => request.path === '/api/invoices' && request.method === 'POST');
    expect(sent.body.items).toEqual([{ product_id: 1, quantity: '100.000', unit_price: '3.0000', vat_rate: '19.00', purchase_order_item_id: 1 }]);
    expect(sent.body.supplier_id).toBe(1);
    expect(sent.body.currency).toBe('EUR');
  });

  test('changing order clears old source data and manual mode removes the link', async ({ page }) => {
    const mock = await mockApi(page, 'CONTABILITATE');
    mock.orders.push({ id: 2, number: 'CA-2', status: 'CLOSED' });
    await page.route('**/api/purchase-orders/2/invoicing', (route) => route.fulfill({ status: 503, json: { message: 'Comandă indisponibilă.' } }));
    await login(page);
    await page.getByRole('button', { name: 'Factură nouă', exact: true }).click();
    await page.getByLabel('Comandă', { exact: true }).selectOption('1');
    await expect(page.getByLabel('Cantitate 1', { exact: true })).toHaveValue('100.000');
    await page.getByLabel('Comandă', { exact: true }).selectOption('2');
    await expect(page.getByRole('alert')).toContainText('Comandă indisponibilă.');
    await expect(page.getByRole('button', { name: 'Salvează ciorna' })).toBeDisabled();
    await expect(page.getByLabel('Cantitate 1', { exact: true })).toHaveCount(0);
    await page.getByLabel('Pornire factură', { exact: true }).selectOption('manual');
    await expect(page.getByLabel('Furnizor', { exact: true })).toBeEnabled();
    await expect(page.getByLabel('Cantitate 1', { exact: true })).toHaveValue('1');
    await expect(page.getByText(/Disponibil de asociat:/)).toHaveCount(0);
  });

  async function fillInvoice(page) {
    await page.getByRole('button', { name: 'Factură nouă', exact: true }).click();
    await page.getByLabel('Pornire factură', { exact: true }).selectOption('manual');
    await page.getByLabel('Furnizor', { exact: true }).selectOption('1');
    await page.getByLabel('Serie (opțional)', { exact: true }).fill(' eur ');
    await page.getByLabel('Număr factură', { exact: true }).fill('00042');
    await page.getByLabel('Data facturii', { exact: true }).fill('2026-10-21');
    await page.getByLabel('Scadență', { exact: true }).fill('2026-11-21');
    await page.getByLabel('Produs 1', { exact: true }).selectOption('1');
    await page.getByLabel('Cantitate 1', { exact: true }).fill('2,500');
    await page.getByLabel('Preț unitar 1', { exact: true }).fill('10,1250');
    await page.getByLabel('TVA (%) 1', { exact: true }).fill('19');
  }

  for (const currency of ['RON', 'EUR']) {
    test(`saves a ${currency} draft using exact decimals and CSRF`, async ({ page }) => {
      const mock = await mockApi(page, 'CONTABILITATE');
      await login(page);
      await fillInvoice(page);
      await page.getByLabel('Monedă', { exact: true }).selectOption(currency);
      await page.getByLabel('Net factură', { exact: true }).fill('25,31');
      await page.getByLabel('TVA factură', { exact: true }).fill('4,81');
      await page.getByLabel('Total factură', { exact: true }).fill('30,12');
      await page.getByRole('button', { name: 'Salvează ciorna' }).click();
      await expect(page.getByText('Factura EUR 00042 a fost salvată ca ciornă.')).toBeVisible();
      const row = page.getByRole('row').filter({ hasText: 'EUR 00042' });
      await expect(row).toContainText('Ciornă');
      await expect(row).toContainText(`30,12 ${currency}`);
      const sent = mock.requests.find((request) => request.path === '/api/invoices' && request.method === 'POST');
      expect(sent.headers['x-csrf-token']).toBe('test-csrf');
      expect(sent.body).toEqual({ supplier_id: 1, series: 'EUR', number: '00042', invoice_date: '2026-10-21', due_date: '2026-11-21', currency, declared_totals: { net_amount: '25.31', vat_amount: '4.81', total_amount: '30.12' }, items: [{ product_id: 1, quantity: '2.500', unit_price: '10.1250', vat_rate: '19' }] });
      expect(mock.requests.filter((request) => request.method === 'POST').map((request) => request.path)).toEqual(['/api/auth/login', '/api/invoices']);
    });
  }

  test('creates a draft without a series from the invoice list', async ({ page }) => {
    const mock = await mockApi(page, 'CONTABILITATE');
    await login(page);
    await page.getByRole('navigation').getByRole('button', { name: 'Facturi', exact: true }).click();
    await fillInvoice(page);
    await page.getByLabel('Serie (opțional)', { exact: true }).fill('');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByText('Factura 00042 a fost salvată ca ciornă.')).toBeVisible();
    expect(mock.requests.find((request) => request.path === '/api/invoices' && request.method === 'POST').body.series).toBe('');
  });

  test('supplier totals require all three amounts and reject invalid decimal input before submission', async ({ page }) => {
    const mock = await mockApi(page, 'CONTABILITATE');
    await login(page);
    await fillInvoice(page);
    await page.getByLabel('Net factură', { exact: true }).fill('25,31');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByRole('alert')).toContainText('Completează toate cele trei totaluri');
    await page.getByLabel('TVA factură', { exact: true }).fill('4,81');
    for (const value of ['-1', '30.121', 'NaN', '1e2']) {
      await page.getByLabel('Total factură', { exact: true }).fill(value);
      await page.getByRole('button', { name: 'Salvează ciorna' }).click();
      await expect(page.getByRole('alert')).toContainText('maximum două zecimale');
    }
    expect(mock.requests.some((request) => request.path === '/api/invoices' && request.method === 'POST')).toBe(false);
  });

  test('validates references, due dates and numeric fields before saving', async ({ page }) => {
    const mock = await mockApi(page, 'CONTABILITATE');
    await login(page);
    await fillInvoice(page);
    await page.getByLabel('Număr factură', { exact: true }).fill('12 34');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByRole('alert')).toContainText('fără spații interne');
    await page.getByLabel('Număr factură', { exact: true }).fill('00042');
    await page.getByLabel('Scadență', { exact: true }).fill('2026-10-20');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByRole('alert')).toContainText('Scadența nu poate');
    await page.getByLabel('Scadență', { exact: true }).fill('2026-11-21');
    for (const [label, value, message, original] of [
      ['Cantitate 1', '0', 'cantitate pozitivă', '2,500'],
      ['Preț unitar 1', '-1', 'preț nenegativ', '10,1250'],
      ['TVA (%) 1', '101', 'TVA între 0 și 100', '19'],
    ]) {
      await page.getByLabel(label, { exact: true }).fill(value);
      await page.getByRole('button', { name: 'Salvează ciorna' }).click();
      await expect(page.getByRole('alert')).toContainText(message);
      await page.getByLabel(label, { exact: true }).fill(original);
    }
    expect(mock.requests.some((request) => request.path === '/api/invoices' && request.method === 'POST')).toBe(false);
  });

  test('can add and remove invoice lines and requires at least one', async ({ page }) => {
    await mockApi(page, 'CONTABILITATE');
    await login(page);
    await fillInvoice(page);
    await page.getByRole('button', { name: 'Adaugă produs', exact: true }).click();
    await expect(page.getByLabel('Produs 2', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Elimină produsul 2', exact: true }).click();
    await expect(page.getByLabel('Produs 2', { exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Elimină produsul 1', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Salvează ciorna' })).toBeDisabled();
  });

  test('preserves entered data when the backend rejects a duplicate invoice', async ({ page }) => {
    await mockApi(page, 'CONTABILITATE');
    await page.route('**/api/invoices', (route) => route.request().method() === 'POST'
      ? route.fulfill({ status: 409, json: { message: 'Factura există deja pentru acest furnizor, serie și număr.' } }) : route.fallback());
    await login(page);
    await fillInvoice(page);
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByRole('alert')).toContainText('Factura există deja');
    await expect(page.getByLabel('Număr factură', { exact: true })).toHaveValue('00042');
    await expect(page.getByLabel('Cantitate 1', { exact: true })).toHaveValue('2,500');
    await page.getByRole('button', { name: 'Anulează', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Factură nouă', exact: true })).toBeVisible();
  });

  test('loads active catalog entries from subsequent pages', async ({ page }) => {
    await mockApi(page, 'CONTABILITATE');
    for (const key of ['products', 'suppliers']) {
      await page.route(`**/api/${key}?*`, (route) => {
        const params = new URL(route.request().url()).searchParams;
        if (params.get('per_page') !== '100') return route.fallback();
        const record = params.get('page') === '1' ? { id: 1, name: 'Inactiv', sku: 'OLD', unit: 'BUC', is_active: false } : { id: 2, name: 'Activ', sku: 'NEW', unit: 'BUC', is_active: true };
        return route.fulfill({ json: { [key]: [record], total: 2 } });
      });
    }
    await login(page);
    await page.getByRole('button', { name: 'Factură nouă', exact: true }).click();
    await page.getByLabel('Pornire factură', { exact: true }).selectOption('manual');
    await expect(page.getByLabel('Furnizor', { exact: true }).getByRole('option', { name: 'Activ', exact: true })).toHaveCount(1);
    await expect(page.getByLabel('Produs 1', { exact: true }).getByRole('option', { name: /NEW/ })).toHaveCount(1);
    await expect(page.getByRole('option', { name: /Inactiv/ })).toHaveCount(0);
  });

  test('explains an empty catalog and disables saving', async ({ page }) => {
    await mockApi(page, 'CONTABILITATE', { emptyCatalog: true });
    await login(page);
    await page.getByRole('button', { name: 'Factură nouă', exact: true }).click();
    await expect(page.getByText('Achizițiile trebuie să adauge un furnizor activ în catalog.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Salvează ciorna' })).toBeDisabled();
  });

  for (const failure of ['network', 'server']) {
    test(`blocks resubmission after uncertain ${failure} failure and fits mobile`, async ({ page }) => {
      await mockApi(page, 'CONTABILITATE');
      await login(page);
      await fillInvoice(page);
      await page.setViewportSize({ width: 390, height: 844 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.route('**/api/invoices', (route) => route.request().method() !== 'POST' ? route.fallback() : failure === 'network'
        ? route.abort('failed') : route.fulfill({ status: 503, json: { message: 'Indisponibil.' } }));
      await page.getByRole('button', { name: 'Salvează ciorna' }).click();
      await expect(page.getByRole('alert')).toContainText('Salvarea nu a putut fi confirmată.');
      await expect(page.getByRole('button', { name: 'Salvează ciorna' })).toBeDisabled();
      await page.getByRole('button', { name: 'Vezi facturile' }).click();
      await expect(page.getByRole('button', { name: 'Factură nouă', exact: true })).toBeVisible();
    });
  }

  test('returns to login if the session expires while saving', async ({ page }) => {
    const mock = await mockApi(page, 'CONTABILITATE');
    await login(page);
    await fillInvoice(page);
    mock.expire();
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    await expect(page.getByRole('heading', { name: 'Intră în contul tău' })).toBeVisible();
  });

  for (const role of ['ADMIN', 'ACHIZITII', 'DEPOZIT']) {
    test(`hides invoice creation from ${role}`, async ({ page }) => {
      await mockApi(page, role);
      await login(page);
      await expect(page.getByRole('button', { name: 'Factură nouă', exact: true })).toHaveCount(0);
    });
  }
});

test.describe('order delivery display', () => {
  for (const role of ['ACHIZITII', 'CONTABILITATE', 'DEPOZIT']) {
    test(`shows supplier and product details with permitted prices for ${role}`, async ({ page }) => {
      await mockApi(page, role);
      await login(page);
      await page.getByRole('navigation').getByRole('button', { name: 'Comenzi', exact: true }).click();
      const row = page.getByRole('row').filter({ hasText: 'CA-1024' });
      await expect(row).toContainText('Furnizor test');
      await expect(row).toContainText('Filtru de aer');
      await expect(row).toContainText('FLT-001');
      await expect(row).toContainText('12,000');
      await expect(row).toContainText('BUC');
      await expect(row).not.toContainText('Furnizor #1');
      if (role === 'DEPOZIT') {
        await expect(page.getByRole('columnheader', { name: 'Preț unitar fără TVA' })).toHaveCount(0);
        await expect(row).not.toContainText('15,00 RON');
      } else {
        await expect(page.getByRole('columnheader', { name: 'Preț unitar fără TVA' })).toBeVisible();
        await expect(row).toContainText('15,00 RON');
      }
    });
  }

  test('keeps several products aligned and searches supplier, product and SKU', async ({ page }) => {
    const mock = await mockApi(page);
    mock.orders[0].items.push({ id: 2, line_number: 2, product_id: 2, sku: 'OIL-002', description: 'Ulei pentru motor', quantity: '2.500', unit: 'L', unit_price: '10.1250' });
    await login(page);
    await page.getByRole('navigation').getByRole('button', { name: 'Comenzi', exact: true }).click();
    const group = page.getByRole('rowgroup', { name: 'Comandă CA-1024' });
    await expect(group.getByRole('row')).toHaveCount(2);
    await expect(group.getByRole('row').filter({ hasText: 'Ulei pentru motor' }).getByRole('cell')).toHaveText(['Ulei pentru motorOIL-002', '2,500', 'L', '10,125 RON']);
    await expect(page.getByRole('button', { name: 'Detalii comandă CA-1024' })).toHaveCount(1);
    for (const query of ['furnizor test', 'ulei pentru motor', 'oil-002']) {
      await page.getByRole('textbox', { name: 'Caută pe pagina curentă' }).fill(query);
      await expect(group).toBeVisible();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test('shows a draft without products without inventing line data', async ({ page }) => {
    const mock = await mockApi(page, 'ACHIZITII', { draftOrder: true });
    mock.orders[0].items = [];
    await login(page);
    const row = page.getByRole('row').filter({ hasText: 'CA-1024' });
    await expect(row).toContainText('Ciornă');
    await expect(row).toContainText('Furnizor test');
    await expect(row).not.toContainText('Filtru de aer');
  });

  for (const [status, label] of [['NOT_RECEIVED', 'Nelivrată'], ['PARTIAL', 'Parțială'], ['COMPLETE', 'Completă']]) {
    test(`shows ${label} separately from the document status`, async ({ page }) => {
      const mock = await mockApi(page);
      mock.orders[0].delivery_status = status;
      await login(page);
      await expect(page.getByRole('row').filter({ hasText: 'CA-1024' })).toContainText(label);
      await expect(page.getByRole('row').filter({ hasText: 'CA-1024' })).toContainText('Confirmată');
    });
  }

  test('shows accepted and remaining quantities per product with the real API envelope', async ({ page }) => {
    await mockApi(page, 'DEPOZIT');
    await login(page);
    await page.getByRole('navigation').getByRole('button', { name: 'Comenzi', exact: true }).click();
    await page.getByRole('button', { name: 'Detalii comandă CA-1024' }).click();
    const delivery = page.getByRole('region', { name: 'Situația livrării' });
    await expect(delivery.getByRole('row').filter({ hasText: 'Filtru de aer', hasNotText: 'suplimentar' }).getByRole('cell')).toHaveText(['Filtru de aer', '100,000', '40,000', '60,000', 'BUC', 'Parțială']);
    await expect(delivery.getByRole('row').filter({ hasText: 'suplimentar' })).toContainText('Nelivrată');
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test('shows zero remaining for a completed delivery', async ({ page }) => {
    const mock = await mockApi(page);
    mock.orders[0].delivery_status = 'COMPLETE';
    await page.route('**/api/purchase-orders/1/delivery', (route) => route.fulfill({ json: { delivery: {
      id: 1, status: 'CONFIRMED', delivery_status: 'COMPLETE', items: [{ id: 1, description: 'Filtru de aer', quantity: '100.000', accepted_quantity: '100.000', remaining_quantity: '0.000', unit: 'BUC', delivery_status: 'COMPLETE' }],
    } } }));
    await login(page);
    await page.getByRole('button', { name: 'Detalii comandă CA-1024' }).click();
    const delivery = page.getByRole('region', { name: 'Situația livrării' });
    await expect(delivery.getByRole('row').filter({ hasText: 'Filtru de aer' })).toContainText('0,000');
    await expect(delivery.getByRole('heading')).toContainText('Completă');
  });

  test('can retry unavailable delivery information', async ({ page }) => {
    await mockApi(page);
    let fail = true;
    await page.route('**/api/purchase-orders/1/delivery', (route) => fail ? route.fulfill({ status: 503, json: { message: 'Livrare indisponibilă.' } }) : route.fallback());
    await login(page);
    await page.getByRole('button', { name: 'Detalii comandă CA-1024' }).click();
    await expect(page.getByRole('alert')).toContainText('Livrare indisponibilă.');
    fail = false;
    await page.getByRole('button', { name: 'Reîncarcă livrarea' }).click();
    await expect(page.getByRole('region', { name: 'Situația livrării' })).toBeVisible();
  });
});

test.describe('receipt confirmation', () => {
  async function openReceipt(page) {
    await login(page);
    await page.getByRole('navigation').getByRole('button', { name: 'Recepții', exact: true }).click();
    await page.getByRole('button', { name: 'Detalii recepție REC-248' }).click();
    await expect(page.getByRole('dialog')).toContainText('Filtru de aer');
  }

  test('accepts 77 with the receipt line ID, version and CSRF and reloads stock', async ({ page }) => {
    const mock = await mockApi(page, 'DEPOZIT', { draftReceipt: true });
    await openReceipt(page);
    await expect(page.getByLabel('Acceptat 1', { exact: true })).toHaveValue('77.000');
    await page.getByLabel('Observații', { exact: true }).fill(' Verificat fizic ');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Recepția a fost confirmată.');
    await expect(page.getByRole('dialog')).toContainText('Versiunea 2');
    await expect(page.getByRole('button', { name: 'Confirmă recepția', exact: true })).toHaveCount(0);
    const sent = mock.requests.filter((request) => request.path === '/api/receipts/2/confirm');
    expect(sent).toHaveLength(1);
    expect(sent[0].headers['x-csrf-token']).toBe('test-csrf');
    expect(sent[0].body).toEqual({ version: 1, reason: 'Verificat fizic', items: [{ id: 11, accepted_quantity: '77.000', rejected_quantity: '0', pending_quantity: '0' }] });
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await expect(page.getByRole('row').filter({ hasText: 'REC-248' })).toContainText('Confirmată');
    await page.getByRole('navigation').getByRole('button', { name: 'Stoc', exact: true }).click();
    await expect(page.getByRole('cell', { name: '101,000', exact: true })).toBeVisible();
  });

  test('separates accepted, rejected and pending quantities', async ({ page }) => {
    await mockApi(page, 'DEPOZIT', { draftReceipt: true });
    await openReceipt(page);
    await page.getByLabel('Acceptat 1', { exact: true }).fill('70');
    await page.getByLabel('Respins 1', { exact: true }).fill('5');
    await page.getByLabel('În așteptare 1', { exact: true }).fill('2');
    await page.getByLabel('Observații', { exact: true }).fill('5 deteriorate, 2 de clarificat');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Recepția a fost confirmată.');
    const row = page.getByRole('dialog').getByRole('row').filter({ hasText: 'Filtru de aer' });
    await expect(row.getByRole('cell')).toHaveText(['Filtru de aer', '77,000', 'BUC', '70', '5', '2']);
    await page.keyboard.press('Escape');
    await page.getByRole('navigation').getByRole('button', { name: 'Stoc', exact: true }).click();
    await expect(page.getByRole('cell', { name: '94,000', exact: true })).toBeVisible();
  });

  test('compares decimal sums exactly and supports several lines', async ({ page }) => {
    const mock = await mockApi(page, 'DEPOZIT', { draftReceipt: true });
    mock.receipts[0].items[0].received_quantity = '0.600';
    mock.receipts[0].items.push({ ...mock.receipts[0].items[0], id: 12, line_number: 2, received_quantity: '3.500' });
    await openReceipt(page);
    await page.getByLabel('Acceptat 1', { exact: true }).fill('0,1');
    await page.getByLabel('Respins 1', { exact: true }).fill('0,2');
    await page.getByLabel('În așteptare 1', { exact: true }).fill('0,3');
    await page.getByLabel('Observații', { exact: true }).fill('Control cantități');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Recepția a fost confirmată.');
    expect(mock.requests.find((request) => request.path === '/api/receipts/2/confirm').body.items).toEqual([
      { id: 11, accepted_quantity: '0.1', rejected_quantity: '0.2', pending_quantity: '0.3' },
      { id: 12, accepted_quantity: '3.500', rejected_quantity: '0', pending_quantity: '0' },
    ]);
  });

  test('rejects invalid quantities and mismatched sums before sending', async ({ page }) => {
    const mock = await mockApi(page, 'DEPOZIT', { draftReceipt: true });
    await openReceipt(page);
    await page.getByLabel('Observații', { exact: true }).fill('Control');
    for (const value of ['-1', '77.0001', 'abc']) {
      await page.getByLabel('Acceptat 1', { exact: true }).fill(value);
      await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
      await expect(page.getByRole('alert')).toContainText('cantități nenegative');
    }
    await page.getByLabel('Acceptat 1', { exact: true }).fill('76');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('trebuie să fie egal cu 77,000');
    expect(mock.requests.some((request) => request.path === '/api/receipts/2/confirm')).toBe(false);
  });

  for (const role of ['ACHIZITII', 'CONTABILITATE']) {
    test(`hides classification from ${role} even with an unexpected draft`, async ({ page }) => {
      await mockApi(page, role, { draftReceipt: true });
      await openReceipt(page);
      await expect(page.getByRole('button', { name: 'Confirmă recepția', exact: true })).toHaveCount(0);
      await expect(page.getByLabel('Acceptat 1', { exact: true })).toHaveCount(0);
    });
  }

  test('hides confirmation for an already confirmed receipt', async ({ page }) => {
    await mockApi(page, 'DEPOZIT');
    await openReceipt(page);
    await expect(page.getByRole('button', { name: 'Confirmă recepția', exact: true })).toHaveCount(0);
  });

  test('requires reload after a version conflict', async ({ page }) => {
    const mock = await mockApi(page, 'DEPOZIT', { draftReceipt: true });
    await openReceipt(page);
    mock.receipts[0].version = 2;
    await page.getByLabel('Observații', { exact: true }).fill('Control');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Recepția a fost modificată.');
    await expect(page.getByRole('button', { name: 'Confirmă recepția', exact: true })).toBeDisabled();
    await page.getByRole('button', { name: 'Actualizează datele' }).click();
    await expect(page.getByRole('dialog')).toContainText('Versiunea 2');
    await page.getByLabel('Observații', { exact: true }).fill('Reverificat');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Recepția a fost confirmată.');
    expect(mock.requests.filter((request) => request.path === '/api/receipts/2/confirm').map((request) => request.body.version)).toEqual([1, 2]);
  });

  test('retains classification after a server validation error and fits mobile', async ({ page }) => {
    await mockApi(page, 'DEPOZIT', { draftReceipt: true });
    await page.route('**/api/receipts/2/confirm', (route) => route.fulfill({ status: 400, json: { message: 'Cantitățile necesită clarificare.' } }));
    await openReceipt(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByLabel('Observații', { exact: true }).fill('Control');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Cantitățile necesită clarificare.');
    await expect(page.getByLabel('Acceptat 1', { exact: true })).toHaveValue('77.000');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test('requires a read after an uncertain result and does not resubmit', async ({ page }) => {
    const mock = await mockApi(page, 'DEPOZIT', { draftReceipt: true });
    await page.route('**/api/receipts/2/confirm', (route) => {
      mock.receipts[0].status = 'CONFIRMED'; mock.receipts[0].version = 2;
      return route.abort('failed');
    });
    await openReceipt(page);
    await page.getByLabel('Observații', { exact: true }).fill('Control');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Confirmarea nu a putut fi verificată.');
    await expect(page.getByRole('button', { name: 'Confirmă recepția', exact: true })).toBeDisabled();
    await page.getByRole('button', { name: 'Actualizează datele' }).click();
    await expect(page.getByRole('dialog')).toContainText('Confirmată');
    await expect(page.getByRole('button', { name: 'Confirmă recepția', exact: true })).toHaveCount(0);
  });

  test('prevents closing and repeating a request in progress', async ({ page }) => {
    await mockApi(page, 'DEPOZIT', { draftReceipt: true });
    let release;
    let attempts = 0;
    const pending = new Promise((resolve) => { release = resolve; });
    await page.route('**/api/receipts/2/confirm', async (route) => { attempts += 1; await pending; await route.fallback(); });
    await openReceipt(page);
    await page.getByLabel('Observații', { exact: true }).fill('Control');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Se confirmă…' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Închide detaliile' })).toBeDisabled();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeVisible();
    expect(attempts).toBe(1);
    release();
    await expect(page.getByRole('dialog')).toContainText('Recepția a fost confirmată.');
  });

  test('removes protected data when the session expires', async ({ page }) => {
    const mock = await mockApi(page, 'DEPOZIT', { draftReceipt: true });
    await openReceipt(page);
    mock.expire();
    await page.getByLabel('Observații', { exact: true }).fill('Control');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Intră în contul tău' })).toBeVisible();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
});

test.describe('order confirmation', () => {
  async function openOrder(page) {
    await login(page);
    await page.getByRole('navigation').getByRole('button', { name: 'Comenzi', exact: true }).click();
    await page.getByRole('button', { name: 'Detalii comandă CA-1024' }).click();
    await expect(page.getByRole('dialog')).toContainText('Filtru de aer');
  }

  test('confirms a draft with its version and CSRF and refreshes the list', async ({ page }) => {
    const { requests } = await mockApi(page, 'ACHIZITII', { draftOrder: true });
    await openOrder(page);
    await page.getByRole('button', { name: 'Confirmă comanda', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Comanda a fost confirmată.');
    await expect(page.getByRole('dialog')).toContainText('Versiunea 2');
    await expect(page.getByRole('button', { name: 'Confirmă comanda', exact: true })).toHaveCount(0);
    const sent = requests.filter((request) => request.path.endsWith('/confirm'));
    expect(sent).toHaveLength(1);
    expect(sent[0].body).toEqual({ version: 1 });
    expect(sent[0].headers['x-csrf-token']).toBe('test-csrf');
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await expect(page.getByRole('row').filter({ hasText: 'CA-1024' })).toContainText('Confirmată');
  });

  test('also confirms from the overview and prevents duplicate submission', async ({ page }) => {
    await mockApi(page, 'ACHIZITII', { draftOrder: true });
    let release;
    let attempts = 0;
    const pending = new Promise((resolve) => { release = resolve; });
    await page.route('**/api/purchase-orders/1/confirm', async (route) => {
      attempts += 1;
      await pending;
      await route.fallback();
    });
    await login(page);
    await page.getByRole('button', { name: 'Detalii comandă CA-1024' }).click();
    await page.getByRole('button', { name: 'Confirmă comanda', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Se confirmă…' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Închide detaliile' })).toBeDisabled();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeVisible();
    expect(attempts).toBe(1);
    release();
    await expect(page.getByRole('dialog')).toContainText('Comanda a fost confirmată.');
  });

  for (const role of ['ACHIZITII', 'DEPOZIT', 'CONTABILITATE']) {
    test(`hides the action for a confirmed order seen by ${role}`, async ({ page }) => {
      await mockApi(page, role);
      await openOrder(page);
      await expect(page.getByRole('button', { name: 'Confirmă comanda', exact: true })).toHaveCount(0);
    });
  }

  for (const role of ['DEPOZIT', 'CONTABILITATE']) {
    test(`hides confirmation from ${role} even if a draft is returned unexpectedly`, async ({ page }) => {
      await mockApi(page, role, { draftOrder: true });
      await openOrder(page);
      await expect(page.getByRole('dialog')).toContainText('Ciornă');
      await expect(page.getByRole('button', { name: 'Confirmă comanda', exact: true })).toHaveCount(0);
    });
  }

  test('requires fresh data after a version conflict and uses the new version', async ({ page }) => {
    const mock = await mockApi(page, 'ACHIZITII', { draftOrder: true });
    await openOrder(page);
    mock.orders[0].version = 2;
    await page.getByRole('button', { name: 'Confirmă comanda', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Comanda a fost modificată.');
    await expect(page.getByRole('button', { name: 'Confirmă comanda', exact: true })).toBeDisabled();
    await page.getByRole('button', { name: 'Actualizează datele' }).click();
    await expect(page.getByRole('dialog')).toContainText('Versiunea 2');
    await page.getByRole('button', { name: 'Confirmă comanda', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Comanda a fost confirmată.');
    expect(mock.requests.filter((request) => request.path.endsWith('/confirm')).map((request) => request.body.version)).toEqual([1, 2]);
  });

  test('reloads after an uncertain response without resending confirmation', async ({ page }) => {
    const mock = await mockApi(page, 'ACHIZITII', { draftOrder: true });
    await openOrder(page);
    await page.route('**/api/purchase-orders/1/confirm', (route) => {
      mock.orders[0].status = 'CONFIRMED'; mock.orders[0].version = 2;
      return route.abort('failed');
    });
    await page.getByRole('button', { name: 'Confirmă comanda', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Confirmarea nu a putut fi verificată.');
    await expect(page.getByRole('button', { name: 'Confirmă comanda', exact: true })).toBeDisabled();
    await page.getByRole('button', { name: 'Actualizează datele' }).click();
    await expect(page.getByRole('dialog')).toContainText('Confirmată');
    await expect(page.getByRole('button', { name: 'Confirmă comanda', exact: true })).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('row').filter({ hasText: 'CA-1024' })).toContainText('Confirmată');
  });

  test('shows server validation and fits mobile', async ({ page }) => {
    await mockApi(page, 'ACHIZITII', { draftOrder: true });
    await page.route('**/api/purchase-orders/1/confirm', (route) => route.fulfill({ status: 400, json: { message: 'Produsul este inactiv.' } }));
    await openOrder(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: 'Confirmă comanda', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Produsul este inactiv.');
    await expect(page.getByRole('dialog')).toContainText('Ciornă');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test('removes the dialog when the session expires on confirmation', async ({ page }) => {
    const mock = await mockApi(page, 'ACHIZITII', { draftOrder: true });
    await openOrder(page);
    mock.expire();
    await page.getByRole('button', { name: 'Confirmă comanda', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Intră în contul tău' })).toBeVisible();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
});
