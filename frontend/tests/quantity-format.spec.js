import { test, expect } from '@playwright/test';
import { quantityText, quantityDifference, parseQuantity } from '../src/receiptQuantities.js';

test('quantity display removes trailing zeros without rounding or losing precision', () => {
  for (const [value, expected] of [
    ['5.000', '5'], ['77.000', '77'], ['78.000', '78'], ['0.000', '0'],
    ['5.500', '5,5'], ['5.050', '5,05'], ['0.001', '0,001'], ['2.125', '2,125'],
    ['999999999999999.999', '999999999999999,999'], ['5,500', '5,5'],
    [5, '5'], [null, '—'], [undefined, '—'],
  ]) expect(quantityText(value)).toBe(expected);
  expect(quantityText('5.500', '.')).toBe('5.5');
  expect(parseQuantity(quantityText('999999999999999.999')).thousandths).toBe(999999999999999999n);
  expect(quantityDifference('10.000', '4.000')).toBe('6');
  expect(quantityDifference('5.500', '0.050')).toBe('5,45');
  expect(quantityDifference('0.000', '0.500')).toBe('-0,5');
});
