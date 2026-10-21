import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { quantityText } from '../src/receiptQuantities.js';

function samplePdf() {
  const stream = 'BT /F1 12 Tf 36 90 Td (Document RURIS pentru test) Tj ET';
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  let content = '%PDF-1.4\n';
  const offsets = [0];
  for (const [index, object] of objects.entries()) { offsets.push(Buffer.byteLength(content)); content += `${index + 1} 0 obj\n${object}\nendobj\n`; }
  const xref = Buffer.byteLength(content);
  content += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets.slice(1)) content += `${String(offset).padStart(10, '0')} 00000 n \n`;
  return Buffer.from(`${content}trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
}

const PDF = samplePdf();
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');

test.describe('real Flask and PostgreSQL flows', () => {
  test.skip(process.env.RURIS_REAL_API !== '1', 'Requires the isolated browser test server.');
  test.setTimeout(120000);

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

  async function setupOrder(page, suffix, amount = 100, unit = 'BUC', currency = 'RON') {
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
    await page.getByLabel('Monedă', { exact: true }).selectOption(currency);
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
    const receipts = [];
    for (const amount of quantities) {
      await navigate(page, 'Recepții');
      await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
      await page.getByLabel('Comandă', { exact: true }).selectOption(String(order.id));
      await page.getByLabel('Document de livrare', { exact: true }).fill(`AV-${order.id}-${amount}`);
      await page.getByLabel('Cantitate sosită 1', { exact: true }).fill(String(amount));
      const saved = page.waitForResponse((response) => response.url().endsWith('/api/receipts') && response.request().method() === 'POST');
      await page.getByRole('button', { name: 'Salvează ciorna' }).click();
      const receipt = (await (await saved).json()).receipt;
      receipts.push(receipt);
      await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
      await page.getByLabel('Observații', { exact: true }).fill('Control fizic browser');
      await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
      await expect(page.getByText('Recepția a fost confirmată.', { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Închide detaliile' }).click();
    }
    await logout(page);
    return receipts;
  }

  async function attach(page, filename = 'factură.pdf', buffer = PDF, mimeType = 'application/pdf') {
    const panel = page.getByRole('region', { name: 'Documente atașate' });
    if (await panel.getByRole('button', { name: 'Documente', exact: true }).getAttribute('aria-expanded') === 'false') await panel.getByRole('button', { name: 'Documente', exact: true }).click();
    await panel.getByLabel('Fișier', { exact: true }).setInputFiles({ name: filename, mimeType, buffer });
    await panel.getByLabel('Observații fișier', { exact: true }).fill('Document justificativ pentru control');
    const saved = page.waitForResponse((response) => /\/api\/documents\/[^/]+\/\d+\/attachments$/.test(response.url()) && response.request().method() === 'POST');
    await panel.getByRole('button', { name: 'Încarcă fișierul', exact: true }).click();
    const response = await saved;
    expect(response.status()).toBe(201);
    const result = await response.json();
    await expect(panel.getByText(filename, { exact: true })).toBeVisible();
    return result;
  }

  async function download(page, name, expected = PDF) {
    const downloaded = page.waitForEvent('download');
    await page.getByRole('button', { name: `Descarcă ${name}`, exact: true }).click();
    const file = await downloaded;
    expect(file.suggestedFilename()).toBe(name);
    const bytes = await readFile(await file.path());
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(createHash('sha256').update(expected).digest('hex'));
  }

  test('commercial order files are shared with accounting and hidden from the warehouse', async ({ page }) => {
    const order = await setupOrder(page, 'DOCORDER', 5);
    await login(page, 'ACHIZITII');
    await navigate(page, 'Comenzi');
    await page.getByRole('button', { name: `Detalii comandă ${order.number}`, exact: true }).click();
    const result = await attach(page, 'ofertă-comercială.pdf');
    await download(page, 'ofertă-comercială.pdf');
    await page.getByRole('region', { name: 'Istoric comandă' }).getByRole('button', { name: 'Istoric', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Istoric comandă' })).toContainText('Fișier atașat');
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await logout(page);
    await login(page, 'DEPOZIT');
    await navigate(page, 'Comenzi');
    await page.getByRole('button', { name: `Detalii comandă ${order.number}`, exact: true }).click();
    await expect(page.getByRole('region', { name: 'Documente atașate' })).toHaveCount(0);
    const denied = await page.evaluate(async (id) => (await fetch(`/api/attachments/${id}/download`)).status, result.attachment.id);
    expect(denied).toBe(403);
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await logout(page);
    await login(page, 'CONTABILITATE');
    await navigate(page, 'Comenzi');
    await page.getByRole('button', { name: `Detalii comandă ${order.number}`, exact: true }).click();
    const panel = page.getByRole('region', { name: 'Documente atașate' });
    await panel.getByRole('button', { name: 'Documente', exact: true }).click();
    await expect(panel.getByText('ofertă-comercială.pdf', { exact: true })).toBeVisible();
    await expect(panel.getByRole('button', { name: 'Încarcă fișierul', exact: true })).toHaveCount(0);
    await download(page, 'ofertă-comercială.pdf');
  });

  test('warehouse evidence follows the confirmed receipt and is readable by purchasing', async ({ page }) => {
    const order = await setupOrder(page, 'DOCRECEIPT', 5);
    const [receipt] = await receive(page, order, [5]);
    await login(page, 'DEPOZIT');
    await navigate(page, 'Recepții');
    await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
    await attach(page, 'aviz.png', PNG, 'image/png');
    await expect(page.getByRole('region', { name: 'Istoric recepție' })).toContainText('Fișier atașat: aviz.png');
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await logout(page);
    await login(page, 'ACHIZITII');
    await navigate(page, 'Recepții');
    await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
    const panel = page.getByRole('region', { name: 'Documente atașate' });
    await panel.getByRole('button', { name: 'Documente', exact: true }).click();
    await expect(panel.getByRole('button', { name: 'Încarcă fișierul', exact: true })).toHaveCount(0);
    await download(page, 'aviz.png', PNG);
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await navigate(page, 'Stoc');
    await expect(page.getByRole('row').filter({ hasText: 'SKU-DOCRECEIPT' })).toContainText('5');
  });

  test('invoice evidence requires reverification, retains withdrawn files and becomes read-only after approval', async ({ page }) => {
    const order = await setupOrder(page, 'DOCINVOICE', 5);
    await receive(page, order, [5]);
    await login(page, 'CONTABILITATE');
    await invoice(page, order, 'DOCINVOICE-001');
    await associate(page);
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
    await attach(page);
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Ciornă');
    await expect(page.getByRole('region', { name: 'Asocieri active' })).toContainText('5');
    const panel = page.getByRole('region', { name: 'Documente atașate' });
    await panel.getByRole('button', { name: 'Retrage factură.pdf', exact: true }).click();
    await panel.getByLabel('Motivul retragerii', { exact: true }).fill('Document inlocuit de furnizor');
    await panel.getByRole('button', { name: 'Confirmă retragerea', exact: true }).click();
    await expect(panel.getByText('Retras', { exact: true })).toBeVisible();
    await download(page, 'factură.pdf');
    await attach(page, 'factură-corectată.pdf');
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
    await page.getByLabel('Observații operație', { exact: true }).fill('Document justificativ controlat');
    await page.getByRole('button', { name: 'Aprobă factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Aprobată');
    await expect(panel.getByRole('button', { name: 'Încarcă fișierul', exact: true })).toHaveCount(0);
    await expect(panel.getByRole('button', { name: /Retrage / })).toHaveCount(0);
    await download(page, 'factură-corectată.pdf');
  });

  async function invoice(page, order, number, price, amount, date = '2026-10-21') {
    await page.getByRole('button', { name: 'Factură nouă', exact: true }).click();
    const sourceLoaded = page.waitForResponse((response) => response.url().includes(`/purchase-orders/${order.id}/invoicing`));
    await page.getByLabel('Comandă', { exact: true }).selectOption(String(order.id));
    const source = (await (await sourceLoaded).json()).order;
    await expect(page.getByLabel('Cantitate 1', { exact: true })).toHaveValue(quantityText(source.items[0].remaining_to_invoice, '.'));
    if (source.invoice_documents.length) await expect(page.getByRole('region', { name: 'Facturi existente pentru comandă' })).toBeVisible();
    await page.getByLabel('Cantitate 1', { exact: true }).fill(amount || order.items[0].quantity);
    if (price) await page.getByLabel('Preț unitar 1', { exact: true }).fill(price);
    await page.getByLabel('Număr factură', { exact: true }).fill(number);
    await page.getByLabel('Data facturii', { exact: true }).fill(date);
    await page.getByLabel('Scadență', { exact: true }).fill('2026-11-21');
    const net = Number(amount || order.items[0].quantity) * Number(price || order.items[0].unit_price);
    await page.getByLabel('Net factură', { exact: true }).fill(net.toFixed(2));
    await page.getByLabel('TVA factură', { exact: true }).fill('0');
    await page.getByLabel('Total factură', { exact: true }).fill(net.toFixed(2));
    const preview = await page.getByRole('region', { name: 'Total calculat din poziții', exact: true }).innerText();
    const saved = page.waitForResponse((response) => response.url().endsWith('/api/invoices') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Salvează ciorna' }).click();
    const created = (await (await saved).json()).invoice;
    for (const key of ['net_amount', 'vat_amount', 'total_amount']) {
      expect(preview).toContain(`${created[key].replace('.', ',')} ${created.currency}`);
    }
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

  test('EUR invoice retries the rate import, uses the cache at approval and records payment', async ({ page }) => {
    const order = await setupOrder(page, 'EURO', 5, 'BUC', 'EUR');
    await receive(page, order, [5]);
    await login(page, 'CONTABILITATE');
    await invoice(page, order, 'EUR-001', undefined, undefined, '2026-10-20');
    await associate(page);
    await page.request.post('http://127.0.0.1:5201/__test__/fx', { data: { mode: 'unavailable' } });
    try {
      await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
      await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Blocată');
      await expect(page.getByRole('region', { name: 'Blocaje factură' })).toContainText('nu a putut fi obtinut sau validat');
      await page.request.post('http://127.0.0.1:5201/__test__/fx', { data: { mode: 'fixture' } });
      await page.getByRole('button', { name: 'Reîncearcă preluarea cursului', exact: true }).click();
      await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
      await expect(page.getByText(/Total în RON:/)).toContainText('51,23');
      await expect(page.getByText(/Curs BNR:/)).toContainText('5,123400');
      await expect(page.getByText(/Data cursului:/)).toContainText('2026-10-20');
      await expect(page.getByRole('link', { name: 'Sursa cursului BNR' })).toHaveAttribute('href', 'https://curs.bnr.ro/files/xml/years/nbrfxrates2026.xml');
      await page.request.post('http://127.0.0.1:5201/__test__/fx', { data: { mode: 'unavailable' } });
      await page.getByRole('button', { name: 'Aprobă factura', exact: true }).click();
      await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Aprobată');
      await page.getByLabel('Referință plată', { exact: true }).fill('OP-EUR-001');
      await page.getByRole('button', { name: 'Înregistrează plata', exact: true }).click();
      await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Plătită');
      await expect(page.getByText(/Total în RON:/)).toContainText('51,23');
      await expect(page.getByRole('button', { name: 'Editează totalurile', exact: true })).toHaveCount(0);
    } finally {
      await page.request.post('http://127.0.0.1:5201/__test__/fx', { data: { mode: 'fixture' } });
    }
  });

  test('an invoice dated on an unpublished day stays blocked with an explicit explanation', async ({ page }) => {
    const order = await setupOrder(page, 'NODATE', 5, 'BUC', 'EUR');
    await receive(page, order, [5]);
    await login(page, 'CONTABILITATE');
    await invoice(page, order, 'NODATE-001', undefined, undefined, '2026-10-17');
    await page.getByLabel('Observații operație', { exact: true }).fill('Verificare data facturii');
    await page.getByRole('button', { name: 'Asociază și verifică', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Blocată');
    await expect(page.getByRole('region', { name: 'Blocaje factură' })).toContainText('nu are curs EUR publicat pentru 2026-10-17');
    await expect(page.getByRole('region', { name: 'Blocaje factură' })).toContainText('nu se foloseste automat cursul altei zile');
    await expect(page.getByRole('button', { name: 'Aprobă factura', exact: true })).toHaveCount(0);
    await expect(page.getByText(/Total în RON:/)).toHaveCount(0);
  });

  test('incorrect supplier totals block the invoice and can be corrected without releasing accepted goods', async ({ page }) => {
    const order = await setupOrder(page, 'TOTALS', 5);
    await receive(page, order, [5]);
    await login(page, 'CONTABILITATE');
    await invoice(page, order, 'TOTALS-001');
    await associate(page);
    await page.getByRole('button', { name: 'Editează totalurile', exact: true }).click();
    await page.getByLabel('Total factură', { exact: true }).fill('10,01');
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Salvează sau anulează editarea totalurilor');
    await expect(page.getByLabel('Total factură', { exact: true })).toHaveValue('10,01');
    await page.getByRole('button', { name: 'Salvează totalurile', exact: true }).click();
    await expect(page.getByText('Totalurile au fost salvate. Verifică din nou factura.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Blocată');
    await expect(page.getByRole('region', { name: 'Comparare totaluri' })).toContainText('0,01');
    await expect(page.getByRole('region', { name: 'Blocaje factură' })).toContainText('diferenta: +0.01 RON');
    await expect(page.getByRole('region', { name: 'Asocieri active' })).toContainText('5');
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole('button', { name: 'Editează totalurile', exact: true }).click();
    await page.getByLabel('Total factură', { exact: true }).fill('10');
    await page.getByLabel('Observații operație', { exact: true }).fill('Corectie conform documentului furnizorului');
    await page.getByRole('button', { name: 'Salvează totalurile', exact: true }).click();
    await expect(page.getByText('Totalurile au fost salvate. Verifică din nou factura.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
    await expect(page.getByRole('region', { name: 'Blocaje factură' })).toHaveCount(0);
    await page.getByRole('region', { name: 'Istoric factură' }).getByRole('button', { name: 'Istoric', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Istoric factură' })).toContainText('Corectie conform documentului furnizorului');
  });

  test('100 ordered, 77 + 23 received, matched, verified, approved and paid', async ({ page }) => {
    const order = await setupOrder(page, 'FULL');
    await receive(page, order, [77, 23]);
    await login(page, 'CONTABILITATE');
    const created = await invoice(page, order, 'FULL-001');
    await associate(page);
    await expect(page.getByRole('region', { name: 'Asocieri active' })).toContainText('77');
    await expect(page.getByRole('region', { name: 'Asocieri active' })).toContainText('23');
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
    await expect(page.getByText(/Total în RON:/)).toContainText('200,00');
    await page.getByRole('button', { name: 'Aprobă factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Aprobată');
    await page.getByLabel('Referință plată', { exact: true }).fill('OP-FULL-001');
    await page.getByRole('button', { name: 'Înregistrează plata', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Plătită');
    await page.getByRole('region', { name: 'Istoric factură' }).getByRole('button', { name: 'Istoric', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Istoric factură' })).toContainText('Plată înregistrată');
    await page.getByRole('region', { name: 'Istoric factură' }).getByText('Modificări', { exact: true }).first().click();
    await expect(page.getByRole('region', { name: 'Istoric factură' })).toContainText('OP-FULL-001');
    await expect(page.getByRole('button', { name: 'Înregistrează plata', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await expect(page.getByRole('row').filter({ hasText: created.number })).toContainText('Plătită');
    await navigate(page, 'Stoc');
    await expect(page.getByRole('row').filter({ hasText: 'SKU-FULL' })).toContainText('100');
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
    await expect(page.getByRole('region', { name: 'Blocaje factură' })).toContainText('100; alocata 77.');
    await expect(page.getByRole('button', { name: 'Aprobă factura', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Înregistrează plata', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await navigate(page, 'Întârzieri');
    await expect(page.getByRole('row').filter({ hasText: order.number })).toContainText('23');
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
    await expect(page.getByRole('region', { name: 'Blocaje factură' })).toContainText('Cantitate facturata 5; alocata 0.');
    await expect(page.getByRole('region', { name: 'Blocaje factură' })).toContainText('Există marfă disponibilă, dar încă neasociată.');
    await page.getByRole('button', { name: 'Asociază și verifică', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Completează observațiile operației.');
    await page.getByLabel('Observații operație', { exact: true }).fill('Asociere recepție 5 m2');
    await page.getByRole('button', { name: 'Asociază și verifică', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
    await expect(page.getByText('Asocierile au fost salvate. Factura este verificată.', { exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Asocieri active' })).toContainText('5');
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
    await page.getByLabel('Net factură', { exact: true }).fill('200');
    await page.getByLabel('Total factură', { exact: true }).fill('200');
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
    await expect(page.getByLabel('În așteptare 1', { exact: true })).toHaveValue('10');
    await page.getByLabel('Observații', { exact: true }).fill('Marfa există fizic, fără comandă');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Acceptă cantitatea', exact: true })).toBeDisabled();
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await navigate(page, 'Stoc');
    await expect(page.getByRole('row').filter({ hasText: 'SKU-UNORDERED' })).toContainText('0');
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
    await expect(page.getByRole('region', { name: 'Acceptări ulterioare' })).toContainText('6');
    await expect(page.getByRole('region', { name: 'Cantități în așteptare' })).toContainText('4');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByLabel('Cantitate de decis 1', { exact: true }).fill('4');
    await page.getByLabel('Observații decizie 1', { exact: true }).fill('Ambalaje deteriorate, respingere 4 bucăți');
    await page.getByRole('button', { name: 'Respinge cantitatea', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Cantități în așteptare' })).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Istoric recepție' })).toContainText('respinse 4 BUC');
    await expect(page.getByRole('region', { name: 'Istoric recepție' })).toContainText('acceptate 6 BUC');
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await navigate(page, 'Stoc');
    await expect(page.getByRole('row').filter({ hasText: 'SKU-UNORDERED' })).toContainText('6');
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
    await page.getByLabel('Comandă', { exact: true }).selectOption(String(order.id));
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
    await expect(page.getByRole('row').filter({ hasText: 'SKU-SURPLUS' })).toContainText('14');
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

  test('clarification emails follow the responsible team and appear in the private journal', async ({ page }) => {
    const order = await setupOrder(page, 'NOTIFY', 10);
    await login(page, 'DEPOZIT');
    await page.getByRole('button', { name: 'Recepție nouă', exact: true }).click();
    await page.getByRole('button', { name: 'Fără comandă', exact: true }).click();
    await page.getByLabel('Furnizor', { exact: true }).selectOption({ label: 'Furnizor NOTIFY' });
    await page.getByLabel('Document de livrare', { exact: true }).fill('AV-NOTIFY');
    await page.getByLabel('Descriere 1', { exact: true }).fill('Marfă pentru clarificare');
    await page.getByLabel('Cantitate sosită 1', { exact: true }).fill('10');
    const saved = page.waitForResponse((response) => response.url().endsWith('/api/receipts/unordered') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Salvează ciorna', exact: true }).click();
    const receipt = (await (await saved).json()).receipt;
    await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
    await page.getByLabel('Observații', { exact: true }).fill('Sosire fără comandă');
    await page.getByRole('button', { name: 'Confirmă recepția', exact: true }).click();
    await expect(page.getByText('Recepția a fost confirmată.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    const first = await page.request.post('http://127.0.0.1:5201/__test__/notifications');
    expect(first.ok()).toBe(true);
    expect((await first.json()).sent).toBeGreaterThan(0);
    await logout(page);

    await login(page, 'ACHIZITII');
    await navigate(page, 'Notificări');
    const buyer = page.locator('.notification-entry').filter({ hasText: 'clarificari receptii' });
    await buyer.locator('summary').click();
    await expect(buyer).toContainText(receipt.number);
    await expect(buyer).toContainText('10.000 BUC');
    await expect(buyer).toContainText('Acceptat de server');
    await navigate(page, 'Clarificări');
    await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
    await page.getByLabel('Comandă pentru poziția 1', { exact: true }).selectOption({ label: order.number });
    await expect(page.getByLabel('Produs comandat 1', { exact: true })).toHaveValue(String(order.items[0].id));
    await page.getByLabel('Observații decizie 1', { exact: true }).fill('Comandă identificată');
    await page.getByRole('button', { name: 'Asociază comanda', exact: true }).click();
    await expect(page.getByText('Comanda a fost asociată. Marfa așteaptă decizia Depozitului.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    const second = await page.request.post('http://127.0.0.1:5201/__test__/notifications');
    expect(second.ok()).toBe(true);
    expect((await second.json()).sent).toBeGreaterThan(0);
    await logout(page);

    await login(page, 'DEPOZIT');
    await navigate(page, 'Notificări');
    const warehouse = page.locator('.notification-entry').filter({ hasText: 'marfa in asteptarea acceptarii' });
    await warehouse.locator('summary').click();
    await expect(warehouse).toContainText(receipt.number);
    await expect(warehouse).toContainText('10.000 BUC');
    await expect(page.locator('.notification-entry').filter({ hasText: 'facturi blocate' })).toHaveCount(0);
    await navigate(page, 'Comenzi');
    await page.getByRole('button', { name: `Detalii comandă ${order.number}`, exact: true }).click();
    const loaded = page.waitForResponse((response) => response.url().includes(`/api/purchase-orders/${order.id}/history`));
    await page.getByRole('region', { name: 'Istoric comandă' }).getByRole('button', { name: 'Istoric', exact: true }).click();
    const history = await (await loaded).json();
    expect(JSON.stringify(history)).not.toMatch(/unit_price|vat_rate|currency/);
    await expect(page.getByRole('region', { name: 'Istoric comandă' })).toContainText('Comandă confirmată');
  });

  test('cancelling a duplicate releases its goods while retaining evidence and history', async ({ page }) => {
    const order = await setupOrder(page, 'CANCEL', 5);
    await receive(page, order, [5]);
    await login(page, 'CONTABILITATE');
    const first = await invoice(page, order, 'CANCEL-001');
    await associate(page);
    await attach(page, 'duplicat.pdf');
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    const second = await invoice(page, order, 'CANCEL-002');
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Blocată');
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await page.getByRole('button', { name: `Detalii factură ${first.number}`, exact: true }).click();
    await page.getByRole('button', { name: 'Anulează factura', exact: true }).click();
    await page.getByLabel('Motivul anulării', { exact: true }).fill('Factura introdusa de doua ori');
    await page.getByRole('button', { name: 'Confirmă anularea', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Anulată');
    await expect(page.getByRole('region', { name: 'Asocieri active' })).toHaveCount(0);
    const panel = page.getByRole('region', { name: 'Documente atașate' });
    await panel.getByRole('button', { name: 'Documente', exact: true }).click();
    await expect(panel.getByRole('button', { name: 'Încarcă fișierul', exact: true })).toHaveCount(0);
    await download(page, 'duplicat.pdf');
    const history = page.getByRole('region', { name: 'Istoric factură' });
    await history.getByRole('button', { name: 'Istoric', exact: true }).click();
    await expect(history).toContainText('Factură anulată');
    await expect(history).toContainText('Factura introdusa de doua ori');
    const context = await page.request.get(`/api/purchase-orders/${order.id}/invoicing`);
    const source = (await context.json()).order;
    expect(source.items[0].registered_quantity).toBe('5.000');
    expect(source.items[0].available_quantity).toBe('5.000');
    expect(source.invoice_documents.find((row) => row.id === first.id).status).toBe('CANCELLED');
    await page.getByRole('button', { name: 'Închide detaliile' }).click();
    await page.getByRole('button', { name: `Detalii factură ${second.number}`, exact: true }).click();
    await associate(page);
    await page.getByRole('button', { name: 'Verifică factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Verificată');
    await page.getByRole('button', { name: 'Aprobă factura', exact: true }).click();
    await expect(page.getByRole('dialog').locator('.document-meta')).toContainText('Aprobată');
    await expect(page.getByRole('button', { name: 'Anulează factura', exact: true })).toHaveCount(0);
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
