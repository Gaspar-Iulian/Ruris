import { parseQuantity, quantityText } from './receiptQuantities.js';

function display(value) {
  const absolute = value < 0n ? -value : value;
  return `${value < 0n ? '-' : ''}${quantityText(`${absolute / 1000n}.${String(absolute % 1000n).padStart(3, '0')}`)}`;
}

export default function ReceiptBalance({ received, values, unit }) {
  const amounts = Object.values(values).map(parseQuantity);
  const total = parseQuantity(received);
  const difference = total && amounts.every(Boolean) ? total.thousandths - amounts.reduce((sum, item) => sum + item.thousandths, 0n) : null;
  return <p className={`quantity-balance ${difference === 0n ? 'balance-ok' : 'balance-warning'}`} aria-live="polite">
    {difference === null ? 'Completează cantitățile pentru verificarea repartizării.' : difference === 0n
      ? `Cantități repartizate integral: ${quantityText(received)} ${unit}.`
      : difference > 0n ? `De repartizat: ${display(difference)} ${unit}.`
        : `Depășire față de cantitatea sosită: ${display(-difference)} ${unit}.`}
  </p>;
}

export function DeliveryQuantityHint({ received, remaining, unit }) {
  const amount = parseQuantity(received);
  const rest = parseQuantity(remaining);
  if (!amount || !rest || amount.thousandths <= rest.thousandths) return null;
  return <p className="quantity-balance balance-warning" aria-live="polite">Surplus față de restul comenzii: {display(amount.thousandths - rest.thousandths)} {unit}. Se clarifică la confirmarea recepției.</p>;
}
