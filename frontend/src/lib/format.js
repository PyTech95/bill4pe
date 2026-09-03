export const inr = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(n) || 0);

export const todayISO = () => new Date().toISOString().slice(0, 10);

export const addDaysISO = (days) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};

export const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
};

export const upiLink = ({ upiId, name, amount, invoiceNumber }) =>
  `upi://pay?pa=${encodeURIComponent(upiId)}&pn=${encodeURIComponent(name || "bill4pe")}&am=${Number(amount).toFixed(2)}&cu=INR&tn=${encodeURIComponent("Invoice " + invoiceNumber)}`;

export const GST_SLABS = [0, 5, 12, 18, 28];

export function computeTotals(items, discountPct, interState) {
  let subtotal = 0;
  let tax = 0;
  for (const it of items) {
    const net = (Number(it.qty) || 0) * (Number(it.rate) || 0) * (1 - (Number(discountPct) || 0) / 100);
    subtotal += net;
    tax += (net * (Number(it.gst_rate) || 0)) / 100;
  }
  subtotal = Math.round(subtotal * 100) / 100;
  tax = Math.round(tax * 100) / 100;
  const total = Math.round((subtotal + tax) * 100) / 100;
  if (interState) return { subtotal, cgst: 0, sgst: 0, igst: tax, tax, total };
  const half = Math.round((tax / 2) * 100) / 100;
  return { subtotal, cgst: half, sgst: Math.round((tax - half) * 100) / 100, igst: 0, tax, total };
}
