function scaled(value, scale, digits) {
  const text = String(value ?? '').trim().replace(',', '.');
  if (!new RegExp(`^[0-9]{1,${digits}}(?:\\.[0-9]{1,${scale}})?$`).test(text)) return null;
  const [whole, fraction = ''] = text.split('.');
  return BigInt(whole) * 10n ** BigInt(scale) + BigInt(fraction.padEnd(scale, '0'));
}

const roundHalfUp = (value, divisor) => (value + divisor / 2n) / divisor;
const amountLimit = 10n ** 18n;

export function calculateLine(line) {
  const quantity = scaled(line.quantity, 3, 15);
  const price = scaled(line.unit_price, 4, 14);
  const rate = scaled(line.vat_rate, 2, 3);
  if (quantity === null || quantity === 0n || price === null || rate === null || rate > 10000n) return null;
  // Round each line before adding document totals.
  const net_amount = roundHalfUp(quantity * price, 100000n);
  const vat_amount = roundHalfUp(net_amount * rate, 10000n);
  const total_amount = net_amount + vat_amount;
  return total_amount < amountLimit ? { net_amount, vat_amount, total_amount } : null;
}

export function calculateTotals(lines) {
  if (!lines.length) return null;
  const totals = { net_amount: 0n, vat_amount: 0n, total_amount: 0n };
  for (const line of lines) {
    const amounts = calculateLine(line);
    if (!amounts) return null;
    for (const key of Object.keys(totals)) totals[key] += amounts[key];
  }
  return totals.total_amount < amountLimit ? totals : null;
}

export const parseMoney = (value) => scaled(value, 2, 16);

export function moneyInput(cents) {
  const absolute = cents < 0n ? -cents : cents;
  return `${cents < 0n ? '-' : ''}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`;
}

export function moneyText(cents, currency) {
  return cents === null || cents === undefined ? '—' : `${moneyInput(cents).replace('.', ',')} ${currency}`;
}
