import { test, expect } from '@playwright/test';
import { calculateLine, calculateTotals, moneyInput, moneyText, parseMoney } from '../src/amounts.js';

test('money preview follows per-line decimal rounding used by the server', () => {
  expect(calculateLine({ quantity: '5', unit_price: '15', vat_rate: '19' })).toEqual({ net_amount: 7500n, vat_amount: 1425n, total_amount: 8925n });
  expect(calculateLine({ quantity: '2,500', unit_price: '10,1250', vat_rate: '19' })).toEqual({ net_amount: 2531n, vat_amount: 481n, total_amount: 3012n });
  expect(calculateLine({ quantity: '1', unit_price: '0.005', vat_rate: '50' })).toEqual({ net_amount: 1n, vat_amount: 1n, total_amount: 2n });
  expect(calculateTotals(Array(2).fill({ quantity: '1', unit_price: '0.005', vat_rate: '0' }))).toEqual({ net_amount: 2n, vat_amount: 0n, total_amount: 2n });
});

test('money preview preserves large values and rejects incomplete or out-of-range totals', () => {
  const large = calculateLine({ quantity: '1', unit_price: '99999999999999.9999', vat_rate: '0' });
  expect(large.net_amount).toBe(10000000000000000n);
  expect(moneyText(large.total_amount, 'EUR')).toBe('100000000000000,00 EUR');
  expect(moneyInput(-1n)).toBe('-0.01');
  expect(parseMoney('89,25')).toBe(8925n);
  expect(parseMoney('89.255')).toBeNull();
  for (const changes of [{ quantity: '0' }, { quantity: '' }, { unit_price: '-1' }, { vat_rate: '101' }, { quantity: '1e3' }, { quantity: '100', unit_price: '99999999999999.9999' }]) {
    expect(calculateLine({ quantity: '1', unit_price: '15', vat_rate: '19', ...changes })).toBeNull();
  }
  expect(calculateTotals([])).toBeNull();
  expect(calculateTotals([{ quantity: '1', unit_price: '15', vat_rate: '19' }, { quantity: '' }])).toBeNull();
});
