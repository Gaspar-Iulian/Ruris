import { test, expect } from '@playwright/test';

test.describe('real Flask and PostgreSQL flows', () => {
  test.skip(process.env.RURIS_REAL_API !== '1', 'Requires the isolated browser test server.');
  test.setTimeout(120000);

  test.beforeEach(async ({ page }) => {
    await page.route('**/api/**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const headers = { ...request.headers(), origin: 'http://127.0.0.1:5201' };
      delete headers.host;
      const response = await route.fetch({ url: `http://127.0.0.1:5201${url.pathname}${url.search}`, headers });
      await route.fulfill({ response });
    });
  });

  async function login(page, role) {
    await page.goto('/');
    await page.getByLabel('Adresă de email').fill(`${role.toLowerCase()}@browser.example.com`);
    await page.getByLabel('Parolă', { exact: true }).fill('Browser-test-2026!');
    await page.getByRole('button', { name: 'Autentificare', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Privire de ansamblu' })).toBeVisible();
  }

  async function logout(page) {
    await page.getByRole('button', { name: 'Deconectare', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Intră în contul tău' })).toBeVisible();
  }

  async function navigate(page, name) {
    const toggle = page.getByRole('button', { name: 'Deschide meniul' });
    if (await toggle.isVisible()) await toggle.click();
    await page.getByRole('navigation').getByRole('button', { name, exact: true }).click();
  }

  async function setupOrder(page, suffix, amount = 100, unit = 'BUC') {
    await login(page, 'ACHIZITII');
    await navigate(page, 'Furnizori');
    await page.getByRole('button', { name: 'Furnizor nou', exact: true }).click();
    await page.getByLabel('Denumire', { exact: true }).fill(`Furnizor ${suffix}`);
    await page.getByLabel('Cod fiscal', { exact: true }).fill(`TEST${suffix}`);
    await page.getByRole('button', { name: 'Salvează', exact: true }).click();
    await expect(page.getByText(`Furnizorul Furnizor ${suffix} a fost salvat.`)).toBeVisible();
    await navigate(page, 'Produse');
    await page.getByRole('button', { name: 'Produs nou', exact: true }).click();
    await page.getByLabel('Denumire', { exact: true }).fill(`Produs ${suffix}`);
    await page.getByLabel('Cod produs', { exact: true }).fill(`SKU-${suffix}`);
    await page.getByLabel('Unitate de măsură', { exact: true }).selectOption(unit);
    await page.getByRole('button', { name: 'Salvează', exact: true }).click();
    await expect(page.getByText(`Produsul Produs ${suffix} a fost salvat.`)).toBeVisible();
    await navigate(page, 'Comenzi');
    await page.getByRole('button', { name: 'Comandă nouă', exact: true }).click();
    await page.getByLabel('Furnizor', { exact: true }).selectOption({ label: `Furnizor ${suffix}` });
    await page.getByLabel('Produs 1', { exact: true }).selectOption({ label: `SKU-${suffix} · Produs ${suffix} (${unit})` });
    await page.getByLabel('Cantitate 1', { exact: true }).fill(String(amount));
    await page.getByLabel('Preț unitar 1', { exact: true }).fill('2');
    await page.getByLabel('TVA (%) 1', { exact: true }).fill('0');
    await page.getByLabel('Termen 1', { exact: true }).fill('2026-10-20');
    const saved = page.waitForResponse((response) => response.url().endsWith('/api/purchase-orders') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    const order = (await (await saved).json()).order;
    await page.getByRole('button', { name: `Detalii comandă ${order.number}`, exact: true }).click();
    await page.getByRole('button', { name: 'Confirmă comanda', exact: true }).click();
    await expect(page.getByText('Comanda a fost confirmată.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await logout(page);
    return order;
  }

  async function receive(page, order, quantities) {
    await login(page, 'DEPOZIT');
    for (const amount of quantities) {
      await navigate(page, 'Recepții');
      await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
      await page.getByLabel('Comandă', { exact: true }).selectOption({ label: order.number });
      await page.getByLabel('Document de livrare', { exact: true }).fill(`AV-${order.id}-${amount}`);
      await page.getByLabel('Cantitate sosită 1', { exact: true }).fill(String(amount));
      const saved = page.waitForResponse((response) => response.url().endsWith('/api/receipts') && response.request().method() === 'POST');
      await page.getByRole('button', { name: 'Salvează ciorna' }).click();
      const receipt = (await (await saved).json()).receipt;
      await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
      await page.getByLabel('Observații', { exact: true }).fill('Control fizic browser');
      await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
      await expect(page.getByText('Recepția a fost confirmată.', { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Închide detaliile' }).click();
    }
    await logout(page);
  }

  async function invoice(page, order, number, price, amount) {
    await page.getByRole('button', { name: 'Factură nouă', exact: true }).click();
    await page.getByLabel('Comandă', { exact: true }).selectOption({ label: order.number });
    await expect(page.getByLabel('Cantitate 1', { exact: true })).toHaveValue(order.items[0].quantity);
    if (amount) await page.getByLabel('Cantitate 1', { exact: true }).fill(amount);
    if (price) await page.getByLabel('Preț unitar 1', { exact: true }).fill(price);
    await page.getByLabel('Număr factură', { exact: true }).fill(number);
    await page.getByLabel('Data facturii', { exact: true }).fill('2026-10-21');
    await page.getByLabel('Scadență', { exact: true }).fill('2026-11-21');
    const saved = page.waitForResponse((response) => response.url().endsWith('/api/invoices') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    const created = (await (await saved).json()).invoice;
    await page.getByRole('button', { name: `Detalii factură ${created.number}`, exact: true }).click();
    await expect(page.getByRole('region', { name: 'Procesare factură' })).toBeVisible();
    return created;
  }

  async function associate(page) {
    await page.getByLabel('Observații operație', { exact: true }).fill('Control documente browser');
    await page.getByRole('button', { name: 'Propune asocierea', exact: true }).click();
    await page.getByRole('button', { name: 'Salvează asocierile', exact: true }).click();
    await expect(page.getByText('Asocierile au fost salvate.', { exact: true })).toBeVisible();
  }

  test('100 ordered, 77 + 23 received, matched, verified, approved and paid', async ({ page }) => {
    const order = await setupOrder(page, 'FULL');
    await receive(page, order, [77, 23]);
    await login(page, 'CONTABILITATE');
    const created = await invoice(page, order, 'FULL-001');
    await associate(page);
    await expect(page.getByRole('region', { name: 'Asocieri active' })).toContainText('77,000');
    await expect(page.getByRole('region', { name: 'Asocieri active' })).toContainText('23,000');
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
    await expect(page.getByText(/Total în RON:/)).toContainText('200,00');
    await page.getByRole('button', { name: 'Aprobă factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Aprobată');
    await page.getByLabel('Referință plată', { exact: true }).fill('OP-FULL-001');
    await page.getByRole('button', { name: 'Înregistrează plata', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Plătită');
    await expect(page.getByRole('button', { name: 'Înregistrează plata', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await expect(page.getByRole('row').filter({ hasText: created.number })).toContainText('Plătită');
    await navigate(page, 'Stoc');
    await expect(page.getByRole('row').filter({ hasText: 'SKU-FULL' })).toContainText('100,000');
    await navigate(page, 'Comenzi');
    await expect(page.getByRole('row').filter({ hasText: order.number })).toContainText('Completă');
    await navigate(page, 'Întârzieri');
    await expect(page.getByRole('cell', { name: order.number, exact: true })).toHaveCount(0);
  });

  test('100 invoiced but only 77 accepted stays blocked', async ({ page }) => {
    const order = await setupOrder(page, 'SHORT');
    await receive(page, order, [77]);
    await login(page, 'CONTABILITATE');
    await invoice(page, order, 'SHORT-001');
    await page.getByLabel('Observații operație', { exact: true }).fill('Control documente browser');
    await page.getByRole('button', { name: 'Asociază și verifică', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Blocată');
    await expect(page.getByRole('region', { name: 'Blocaje factură' })).toContainText('100.000; alocata 77.000');
    await expect(page.getByRole('button', { name: 'Aprobă factura', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Înregistrează plata', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await navigate(page, 'Întârzieri');
    await expect(page.getByRole('row').filter({ hasText: order.number })).toContainText('23,000');
  });

  test('a blocked invoice for 5 square meters is matched and verified in one action', async ({ page }) => {
    const order = await setupOrder(page, 'QUICK', 5, 'M2');
    await receive(page, order, [5]);
    await login(page, 'CONTABILITATE');
    const created = await invoice(page, order, 'QUICK-001');
    const blocked = await page.evaluate(async ({ id, version }) => {
      const token = document.cookie.split('; ').find((cookie) => cookie.startsWith('csrf_access_token=')).split('=').slice(1).join('=');
      const response = await fetch(`/api/invoices/${id}/verify`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': decodeURIComponent(token) }, body: JSON.stringify({ version }) });
      return response.json();
    }, { id: created.id, version: created.version });
    expect(blocked.invoice.status).toBe('BLOCKED');
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await page.getByRole('button', { name: 'Detalii factură QUICK-001', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Blocaje factură' })).toContainText('Există marfă disponibilă, dar încă neasociată.');
    await page.getByRole('button', { name: 'Asociază și verifică', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Completează observațiile operației.');
    await page.getByLabel('Observații operație', { exact: true }).fill('Asociere recepție 5 m2');
    await page.getByRole('button', { name: 'Asociază și verifică', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
    await expect(page.getByText('Asocierile au fost salvate. Factura este verificată.', { exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Asocieri active' })).toContainText('5,000');
    await expect(page.getByRole('region', { name: 'Blocaje factură' })).toHaveCount(0);
  });

  test('wrong price is visible, blocked and can be corrected before matching', async ({ page }) => {
    const order = await setupOrder(page, 'PRICE');
    await receive(page, order, [100]);
    await login(page, 'CONTABILITATE');
    await invoice(page, order, 'PRICE-001', '3');
    await expect(page.getByText(/Preț diferit de comandă/)).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Blocată');
    await page.getByRole('button', { name: 'Corectează factura', exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByLabel('Preț unitar 1', { exact: true }).fill('2');
    await page.getByLabel('Motivul corectării', { exact: true }).fill('Factura corectată de furnizor');
    await page.getByRole('button', { name: 'Salvează modificările', exact: true }).click();
    await expect(page.getByText('Factura a fost corectată. Este necesară verificarea.')).toBeVisible();
    await expect(page.getByText(/Preț diferit de comandă/)).toHaveCount(0);
    await associate(page);
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
  });

  test('unordered unknown goods are clarified, partly accepted, rejected and invoiced', async ({ page }) => {
    const order = await setupOrder(page, 'UNORDERED', 10);
    await login(page, 'DEPOZIT');
    await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
    await page.getByRole('button', { name: 'Fără comandă', exact: true }).click();
    await page.getByLabel('Furnizor', { exact: true }).selectOption({ label: 'Furnizor UNORDERED' });
    await page.getByLabel('Document de livrare', { exact: true }).fill('AV-UNKNOWN');
    await page.getByLabel('Descriere 1', { exact: true }).fill('Marfă de identificat');
    await page.getByLabel('Cantitate sosită 1', { exact: true }).fill('10');
    const saved = page.waitForResponse((response) => response.url().endsWith('/api/receipts/unordered') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    const receipt = (await (await saved).json()).receipt;
    await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
    await expect(page.getByLabel('Acceptat 1', { exact: true })).toBeDisabled();
    await expect(page.getByLabel('În așteptare 1', { exact: true })).toHaveValue('10.000');
    await page.getByLabel('Observații', { exact: true }).fill('Marfa există fizic, fără comandă');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Acceptă cantitatea', exact: true })).toBeDisabled();
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await navigate(page, 'Stoc');
    await expect(page.getByRole('row').filter({ hasText: 'SKU-UNORDERED' })).toContainText('0,000');
    await logout(page);

    await login(page, 'CONTABILITATE');
    const created = await invoice(page, order, 'PENDING-001', undefined, '6');
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Blocată');
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await logout(page);

    await login(page, 'ACHIZITII');
    await navigate(page, 'Clarificări');
    await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
    await page.getByLabel('Comandă pentru poziția 1', { exact: true }).selectOption({ label: order.number });
    await expect(page.getByLabel('Produs comandat 1', { exact: true })).toHaveValue(String(order.items[0].id));
    await page.getByLabel('Observații decizie 1', { exact: true }).fill('Identificare și acoperire comercială');
    await page.getByRole('button', { name: 'Asociază comanda', exact: true }).click();
    await expect(page.getByText('Comanda a fost asociată. Marfa așteaptă decizia Depozitului.', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Acceptă cantitatea', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await logout(page);

    await login(page, 'DEPOZIT');
    await navigate(page, 'Clarificări');
    await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByLabel('Cantitate de decis 1', { exact: true }).fill('6');
    await page.getByLabel('Observații decizie 1', { exact: true }).fill('Acceptare parțială 6 bucăți');
    await page.getByRole('button', { name: 'Acceptă cantitatea', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Acceptări ulterioare' })).toContainText('6,000');
    await expect(page.getByRole('region', { name: 'Cantități în așteptare' })).toContainText('4,000');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByLabel('Cantitate de decis 1', { exact: true }).fill('4');
    await page.getByLabel('Observații decizie 1', { exact: true }).fill('Ambalaje deteriorate, respingere 4 bucăți');
    await page.getByRole('button', { name: 'Respinge cantitatea', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Cantități în așteptare' })).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Istoric recepție' })).toContainText('respinse 4,000 BUC');
    await expect(page.getByRole('region', { name: 'Istoric recepție' })).toContainText('acceptate 6,000 BUC');
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await navigate(page, 'Stoc');
    await expect(page.getByRole('row').filter({ hasText: 'SKU-UNORDERED' })).toContainText('6,000');
    await navigate(page, 'Clarificări');
    await expect(page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true })).toHaveCount(0);
    await logout(page);

    await page.setViewportSize({ width: 1440, height: 1000 });
    await login(page, 'CONTABILITATE');
    await navigate(page, 'Facturi');
    await page.getByRole('button', { name: `Detalii factură ${created.number}`, exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Blocată');
    await page.getByLabel('Observații operație', { exact: true }).fill('Cantitate acceptată și documentată');
    await page.getByRole('button', { name: 'Asociază și verifică', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
    await page.getByRole('button', { name: 'Aprobă factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Aprobată');
  });

  test('a surplus keeps the initial order and uses a supplementary order for the rest', async ({ page }) => {
    const order = await setupOrder(page, 'SURPLUS', 10);
    await login(page, 'DEPOZIT');
    await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
    await page.getByLabel('Comandă', { exact: true }).selectOption({ label: order.number });
    await page.getByLabel('Document de livrare', { exact: true }).fill('AV-SURPLUS');
    await page.getByLabel('Cantitate sosită 1', { exact: true }).fill('14');
    const saved = page.waitForResponse((response) => response.url().endsWith('/api/receipts') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    const receipt = (await (await saved).json()).receipt;
    await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
    await page.getByLabel('Acceptat 1', { exact: true }).fill('10');
    await page.getByLabel('În așteptare 1', { exact: true }).fill('4');
    await page.getByLabel('Observații', { exact: true }).fill('Surplus de 4 bucăți');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByText('Recepția a fost confirmată.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await logout(page);

    await login(page, 'ACHIZITII');
    await page.getByRole('button', { name: 'Comandă nouă', exact: true }).click();
    await page.getByLabel('Furnizor', { exact: true }).selectOption({ label: 'Furnizor SURPLUS' });
    await page.getByLabel('Produs 1', { exact: true }).selectOption({ label: 'SKU-SURPLUS · Produs SURPLUS (BUC)' });
    await page.getByLabel('Cantitate 1', { exact: true }).fill('4');
    await page.getByLabel('Preț unitar 1', { exact: true }).fill('2');
    await page.getByLabel('TVA (%) 1', { exact: true }).fill('0');
    await page.getByLabel('Termen 1', { exact: true }).fill('2026-10-21');
    const secondSaved = page.waitForResponse((response) => response.url().endsWith('/api/purchase-orders') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    const second = (await (await secondSaved).json()).order;
    await page.getByRole('button', { name: `Detalii comandă ${second.number}`, exact: true }).click();
    await page.getByRole('button', { name: 'Confirmă comanda', exact: true }).click();
    await expect(page.getByText('Comanda a fost confirmată.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await navigate(page, 'Clarificări');
    await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
    await page.getByLabel('Comandă pentru poziția 1', { exact: true }).selectOption({ label: second.number });
    await expect(page.getByLabel('Produs comandat 1', { exact: true })).toHaveValue(String(second.items[0].id));
    await page.getByLabel('Observații decizie 1', { exact: true }).fill('Comandă suplimentară pentru surplus');
    await page.getByRole('button', { name: 'Asociază comanda', exact: true }).click();
    await expect(page.getByText('Comanda a fost asociată. Marfa așteaptă decizia Depozitului.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await logout(page);

    await login(page, 'DEPOZIT');
    await navigate(page, 'Clarificări');
    await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
    await page.getByLabel('Cantitate de decis 1', { exact: true }).fill('4');
    await page.getByLabel('Observații decizie 1', { exact: true }).fill('Acceptat pe comanda suplimentară');
    await page.getByRole('button', { name: 'Acceptă cantitatea', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Acceptări ulterioare' })).toContainText(second.number);
    await expect(page.getByRole('region', { name: 'Cantități în așteptare' })).toHaveCount(0);
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await navigate(page, 'Comenzi');
    await expect(page.getByRole('row').filter({ hasText: order.number })).toContainText('Completă');
    await expect(page.getByRole('row').filter({ hasText: second.number })).toContainText('Completă');
    await navigate(page, 'Stoc');
    await expect(page.getByRole('row').filter({ hasText: 'SKU-SURPLUS' })).toContainText('14,000');
    await logout(page);

    await login(page, 'CONTABILITATE');
    await invoice(page, second, 'SURPLUS-004');
    await page.getByLabel('Observații operație', { exact: true }).fill('Factură pentru surplus acceptat');
    await page.getByRole('button', { name: 'Asociază și verifică', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
    await expect(page.getByRole('region', { name: 'Asocieri active' })).toContainText(second.number);
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await invoice(page, order, 'SURPLUS-010');
    await page.getByLabel('Observații operație', { exact: true }).fill('Factura comenzii inițiale');
    await page.getByRole('button', { name: 'Asociază și verifică', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
    await expect(page.getByRole('region', { name: 'Asocieri active' })).toContainText(order.number);
  });

  test('two invoices cannot consume the same receipt; releasing makes it available', async ({ page }) => {
    const order = await setupOrder(page, 'DOUBLE');
    await receive(page, order, [100]);
    await login(page, 'CONTABILITATE');
    const first = await invoice(page, order, 'DOUBLE-001');
    await associate(page);
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await invoice(page, order, 'DOUBLE-002');
    await page.getByRole('button', { name: 'Propune asocierea', exact: true }).click();
    await expect(page.getByText('Nu există cantități compatibile disponibile pentru asociere.')).toBeVisible();
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Blocată');
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await page.getByRole('button', { name: `Detalii factură ${first.number}`, exact: true }).click();
    await page.getByLabel('Observații operație', { exact: true }).fill('Factura duplicată înlocuită');
    await page.getByRole('button', { name: /Eliberează asocierea #/ }).click();
    await expect(page.getByText('Asocierea a fost eliberată.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await page.getByRole('button', { name: 'Detalii factură DOUBLE-002', exact: true }).click();
    await associate(page);
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
  });
});
