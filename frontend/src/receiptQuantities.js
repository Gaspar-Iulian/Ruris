export function parseQuantity(value) {
  const normalized = String(value ?? '').trim().replace(',', '.');
  if (!/^[0-9]{1,15}(?:\.[0-9]{1,3})?$/.test(normalized)) return null;
  const [whole, fraction = ''] = normalized.split('.');
  return { text: normalized, thousandths: BigInt(whole) * 1000n + BigInt(fraction.padEnd(3, '0')) };
}

export function quantityText(value, separator = ',') {
  if (value === null || value === undefined || value === '') return '—';
  const [whole, fraction = ''] = String(value).replace(',', '.').split('.');
  const decimals = fraction.replace(/0+$/, '');
  return decimals ? `${whole}${separator}${decimals}` : whole;
}

export function quantityDifference(before, after) {
  const first = parseQuantity(before);
  const second = parseQuantity(after);
  if (!first || !second) return '—';
  const difference = first.thousandths - second.thousandths;
  const absolute = difference < 0n ? -difference : difference;
  return `${difference < 0n ? '-' : ''}${quantityText(`${absolute / 1000n}.${String(absolute % 1000n).padStart(3, '0')}`)}`;
}
