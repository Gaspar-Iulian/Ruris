import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

test('restored Docker portal retains stock, paid invoices and attachment bytes', async ({ page }) => {
  test.skip(process.env.RURIS_DOCKER_SMOKE !== '1', 'Requires the isolated Docker smoke database.');
  async function login(role) {
    await page.goto('/');
    await page.getByLabel('Adresă de email').fill(`${role.toLowerCase()}@browser.example.com`);
    await page.getByLabel('Parolă', { exact: true }).fill('Browser-test-2026!');
    await page.getByRole('button', { name: 'Autentificare', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Privire de ansamblu' })).toBeVisible();
  }
  await login('ACHIZITII');
  await page.getByRole('navigation').getByRole('button', { name: 'Stoc', exact: true }).click();
  await expect(page.getByRole('row').filter({ hasText: 'SKU-FULL' })).toContainText('100');
  await expect(page.getByRole('row').filter({ hasText: 'SKU-DOCRECEIPT' })).toContainText('5');
  const response = await page.request.get('/api/receipts');
  expect(response.status()).toBe(200);
  const receipt = (await response.json()).receipts.find((row) => row.line_items.some((item) => item.description === 'Produs DOCRECEIPT'));
  expect(receipt.status).toBe('CONFIRMED');
  await page.getByRole('navigation').getByRole('button', { name: 'Recepții', exact: true }).click();
  await page.getByRole('button', { name: `Detalii recepție ${receipt.number}`, exact: true }).click();
  const attachments = page.getByRole('region', { name: 'Documente atașate' });
  await attachments.getByRole('button', { name: 'Documente', exact: true }).click();
  const downloaded = page.waitForEvent('download');
  await attachments.getByRole('button', { name: 'Descarcă aviz.png', exact: true }).click();
  const bytes = await readFile(await (await downloaded).path());
  const expected = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');
  expect(createHash('sha256').update(bytes).digest('hex')).toBe(createHash('sha256').update(expected).digest('hex'));
  await page.getByRole('button', { name: 'Închide detaliile', exact: true }).click();
  await page.getByRole('button', { name: 'Deconectare', exact: true }).click();
  await login('CONTABILITATE');
  await page.getByRole('navigation').getByRole('button', { name: 'Facturi', exact: true }).click();
  await expect(page.getByRole('rowgroup', { name: 'Factură FULL-001', exact: true })).toContainText('Plătită');
});
