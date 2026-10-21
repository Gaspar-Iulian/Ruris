import { test, expect } from '@playwright/test';

async function portal(page, role) {
  const receipt = { id: 1, number: 'REC-1', supplier_name: 'Furnizor Utilaje', delivery_reference: 'AV-77',
    received_at: '2026-10-21T08:00:00Z', status: 'CONFIRMED', line_items: [
      { id: 1, description: 'Filtru aer', order_number: 'CA-1 / CA-2', unit: 'BUC', received_quantity: '14.000',
        total_accepted_quantity: '14.000', rejected_quantity: '0.000', pending_quantity: '0.000' },
      { id: 2, description: 'Ulei motor', order_number: null, unit: 'L', received_quantity: '8.500',
        total_accepted_quantity: '3.000', rejected_quantity: '1.000', pending_quantity: '4.000' },
    ] };
  const invoice = { id: 1, number: '11', series: 'RR', supplier_name: 'Furnizor Utilaje', currency: 'EUR',
    invoice_date: '2026-10-20', due_date: '2026-11-20', total_amount: '59.50', status: 'BLOCKED', line_items: [
      { id: 1, description: 'Filtru aer', order_number: 'CA-1', quantity: '2.000', unit: 'BUC', unit_price: '10.0000', vat_rate: '19.00', total_amount: '23.80' },
      { id: 2, description: 'Ulei motor', order_number: null, quantity: '3.000', unit: 'L', unit_price: '10.0000', vat_rate: '19.00', total_amount: '35.70' },
    ] };
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/auth/me') return route.fulfill({ json: { user: { id: 1, name: 'Angajat', role } } });
    const data = {
      '/api/receipts': { receipts: [receipt], total: 1 }, '/api/receipts/pending': { receipts: [receipt], total: 1 },
      '/api/invoices': { invoices: [invoice], total: 1 }, '/api/purchase-orders': { orders: [], total: 0 },
      '/api/suppliers': { suppliers: [{ id: 1, name: 'Furnizor Utilaje', is_active: true,
        ...(role === 'DEPOZIT' ? {} : { tax_country: 'RO', tax_id: '123', email: 'vanzari@example.com' }) }], total: 1 },
      '/api/products': { products: [], total: 0 },
      '/api/purchase-orders/overdue': { items: [{ id: 1, order_number: 'CA-1', supplier_name: 'Furnizor Utilaje',
        description: 'Filtru aer', quantity: '100.000', accepted_quantity: '77.000', remaining_quantity: '23.000',
        unit: 'BUC', expected_date: '2026-10-17', days_overdue: 4 }], total: 1 },
    };
    return route.fulfill({ json: data[path] || {} });
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Privire de ansamblu', exact: true })).toBeVisible();
}

async function navigate(page, name) {
  await page.getByRole('navigation').getByRole('button', { name, exact: true }).click();
  return page.locator('.records-panel');
}

for (const role of ['ACHIZITII', 'DEPOZIT', 'CONTABILITATE']) {
  test(`receipt lists show root quantities and filter pending products for ${role}`, async ({ page }) => {
    await portal(page, role);
    const panel = await navigate(page, 'Recepții');
    const group = panel.getByRole('rowgroup', { name: 'Recepție REC-1', exact: true });
    await expect(group.getByRole('row')).toHaveCount(2);
    await expect(group.getByRole('cell', { name: 'Furnizor Utilaje', exact: true })).toHaveCount(1);
    await expect(group.getByRole('cell', { name: '14', exact: true })).toHaveCount(2);
    await expect(group.getByRole('cell', { name: '8,5', exact: true })).toHaveCount(1);
    await expect(group).toContainText('CA-1 / CA-2');
    await expect(panel.getByRole('columnheader', { name: 'Preț unitar fără TVA' })).toHaveCount(0);
    await navigate(page, 'Clarificări');
    await expect(group.getByRole('row')).toHaveCount(1);
    await expect(group).toContainText('Ulei motor');
    await expect(group).not.toContainText('Filtru aer');
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('invoices show supplier names, line values and one document total', async ({ page }) => {
  await portal(page, 'CONTABILITATE');
  const panel = await navigate(page, 'Facturi');
  const group = panel.getByRole('rowgroup', { name: 'Factură RR 11', exact: true });
  await expect(group.getByRole('row')).toHaveCount(2);
  await expect(group.getByRole('cell', { name: 'Furnizor Utilaje', exact: true })).toHaveCount(1);
  await expect(group.getByRole('cell', { name: '59,50 EUR', exact: true })).toHaveCount(1);
  await expect(group.getByRole('cell', { name: '10,00 EUR', exact: true })).toHaveCount(2);
  await expect(group).toContainText('23,80 EUR');
  await expect(group).toContainText('35,70 EUR');
  await expect(panel.getByRole('columnheader', { name: 'Scadență', exact: true })).toBeVisible();
  await expect(group).not.toContainText('Furnizor #');
  await panel.getByRole('textbox').fill('Ulei motor');
  await expect(group).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('overdue list exposes supplier and the delivery balance', async ({ page }) => {
  await portal(page, 'ACHIZITII');
  const panel = await navigate(page, 'Întârzieri');
  for (const value of ['Furnizor Utilaje', '100', '77', '23', 'BUC']) {
    await expect(panel.getByRole('cell', { name: value, exact: true })).toBeVisible();
  }
});

for (const role of ['ACHIZITII', 'DEPOZIT', 'CONTABILITATE']) {
  test(`supplier columns respect the ${role} projection`, async ({ page }) => {
    await portal(page, role);
    const panel = await navigate(page, 'Furnizori');
    await expect(panel.getByRole('cell', { name: 'Furnizor Utilaje', exact: true })).toBeVisible();
    await expect(panel.getByRole('columnheader', { name: 'Cod fiscal', exact: true })).toHaveCount(role === 'DEPOZIT' ? 0 : 1);
    if (role !== 'DEPOZIT') await expect(panel).toContainText('RO123');
  });
}
