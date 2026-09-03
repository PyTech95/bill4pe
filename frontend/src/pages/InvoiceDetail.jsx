import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Copy, Printer, Send, Pencil, Trash2, MessageCircle, QrCode } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";
import { API, fmtErr } from "@/lib/api";
import { inr, fmtDate, upiLink } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";

const MODES = [
  { v: "upi", label: "UPI" },
  { v: "neft", label: "NEFT / IMPS" },
  { v: "cash", label: "Cash" },
  { v: "cheque", label: "Cheque" },
  { v: "other", label: "Other" },
];

export default function InvoiceDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [inv, setInv] = useState(null);
  const [settings, setSettings] = useState(null);
  const [payOpen, setPayOpen] = useState(false);
  const [pay, setPay] = useState({ amount: "", mode: "upi", reference: "", note: "" });
  const [saving, setSaving] = useState(false);

  const load = () => {
    API.get(`/invoices/${id}`)
      .then((r) => {
        setInv(r.data);
        setPay((p) => ({ ...p, amount: r.data.balance_due > 0 ? r.data.balance_due : "" }));
      })
      .catch((e) => {
        toast.error(fmtErr(e));
        navigate("/invoices");
      });
    API.get("/settings").then((r) => setSettings(r.data)).catch(() => {});
  };

  useEffect(load, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!inv) return <div className="text-slate-400 text-sm py-20 text-center">Loading invoice…</div>;

  const link = settings?.upi_id
    ? upiLink({ upiId: settings.upi_id, name: settings.business_name, amount: inv.balance_due, invoiceNumber: inv.invoice_number })
    : null;

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(link);
      toast.success("UPI link copied");
    } catch {
      toast.error("Copy failed — long-press the link instead");
    }
  };

  const recordPayment = async () => {
    setSaving(true);
    try {
      const { data } = await API.post(`/invoices/${id}/payments`, {
        amount: Number(pay.amount), mode: pay.mode, reference: pay.reference, note: pay.note,
      });
      setInv(data);
      setPayOpen(false);
      setPay({ amount: data.balance_due > 0 ? data.balance_due : "", mode: "upi", reference: "", note: "" });
      toast.success(data.status === "paid" ? "Invoice fully paid" : "Payment recorded");
    } catch (e) {
      toast.error(fmtErr(e));
    } finally {
      setSaving(false);
    }
  };

  const sendInvoice = async () => {
    try {
      const { data } = await API.post(`/invoices/${id}/send`);
      setInv(data);
      toast.success("Invoice marked as sent");
    } catch (e) {
      toast.error(fmtErr(e));
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete invoice ${inv.invoice_number}?`)) return;
    try {
      await API.delete(`/invoices/${id}`);
      toast.success("Invoice deleted");
      navigate("/invoices");
    } catch (e) {
      toast.error(fmtErr(e));
    }
  };

  const waText = encodeURIComponent(
    `Invoice ${inv.invoice_number} from ${settings?.business_name || "us"} — Total ${inr(inv.total)}, balance ${inr(inv.balance_due)}.${link ? ` Pay via UPI: ${link}` : ""}`
  );

  return (
    <div data-testid="invoice-detail-page" className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 print-hidden">
        <div className="flex items-center gap-3">
          <Link to="/invoices" data-testid="invoice-detail-back-link" className="p-2 rounded-lg border border-slate-200 bg-white text-slate-500 hover:text-slate-900 transition-colors">
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <h1 className="font-heading text-2xl sm:text-3xl font-bold text-slate-900 font-mono tracking-tight">{inv.invoice_number}</h1>
          <StatusBadge status={inv.status} testid="invoice-detail-status-badge" />
        </div>
        <div className="flex flex-wrap gap-2">
          {inv.status === "draft" && (
            <>
              <Link to={`/invoices/${id}/edit`} data-testid="invoice-detail-edit-btn" className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:border-[#5E35B1] hover:text-[#5E35B1] transition-colors">
                <Pencil className="w-3.5 h-3.5" /> Edit
              </Link>
              <button onClick={sendInvoice} data-testid="invoice-detail-send-btn" className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:border-[#5E35B1] hover:text-[#5E35B1] transition-colors">
                <Send className="w-3.5 h-3.5" /> Mark Sent
              </button>
            </>
          )}
          {inv.status !== "paid" && inv.status !== "draft" && (
            <button onClick={() => setPayOpen(true)} data-testid="invoice-detail-record-payment-btn" className="inline-flex items-center gap-1.5 h-9 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold transition-colors">
              Record Payment
            </button>
          )}
          <a href={`https://wa.me/?text=${waText}`} target="_blank" rel="noreferrer" data-testid="invoice-detail-share-whatsapp-btn" className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:border-emerald-500 hover:text-emerald-600 transition-colors">
            <MessageCircle className="w-3.5 h-3.5" /> WhatsApp
          </a>
          <button onClick={() => window.print()} data-testid="invoice-detail-download-pdf-btn" className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:border-[#5E35B1] hover:text-[#5E35B1] transition-colors">
            <Printer className="w-3.5 h-3.5" /> Print / PDF
          </button>
          <button onClick={remove} data-testid="invoice-detail-delete-btn" className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg border border-rose-200 bg-white text-xs font-semibold text-rose-600 hover:bg-rose-50 transition-colors">
            <Trash2 className="w-3.5 h-3.5" /> Delete
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 sm:gap-6 items-start">
        <div className="xl:col-span-8 card-surface print-sheet p-6 sm:p-10" data-testid="invoice-detail-sheet">
          <div className="flex flex-wrap justify-between gap-6 pb-8 border-b border-slate-100">
            <div>
              <div className="font-heading text-2xl font-bold text-slate-900">{settings?.business_name || "Your Business"}</div>
              {settings?.trade_name && <div className="text-sm text-slate-500">{settings.trade_name}</div>}
              {settings?.address && <div className="text-sm text-slate-500 mt-1 whitespace-pre-line">{settings.address}</div>}
              {settings?.gstin && <div className="text-xs font-mono text-slate-500 mt-1">GSTIN: {settings.gstin}</div>}
            </div>
            <div className="text-right">
              <div className="text-[11px] font-semibold tracking-[0.18em] uppercase text-slate-400">Tax Invoice</div>
              <div className="font-mono text-xl font-bold text-[#5E35B1] mt-1">{inv.invoice_number}</div>
              <div className="text-sm text-slate-500 mt-2">Issued: {fmtDate(inv.issue_date)}</div>
              <div className="text-sm text-slate-500">Due: {fmtDate(inv.due_date)}</div>
            </div>
          </div>

          <div className="py-6 border-b border-slate-100">
            <div className="text-[11px] font-semibold tracking-[0.18em] uppercase text-slate-400 mb-1.5">Billed to</div>
            <div className="font-semibold text-slate-900">{inv.customer_name}</div>
            {inv.customer_address && <div className="text-sm text-slate-500 whitespace-pre-line">{inv.customer_address}</div>}
            {inv.customer_gstin && <div className="text-xs font-mono text-slate-500 mt-1">GSTIN: {inv.customer_gstin}</div>}
          </div>

          <div className="py-6 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-[0.14em] text-slate-400 border-b border-slate-100">
                  <th className="py-2.5 pr-4 font-semibold">Item</th>
                  <th className="py-2.5 pr-4 font-semibold">HSN</th>
                  <th className="py-2.5 pr-4 font-semibold text-right">Qty</th>
                  <th className="py-2.5 pr-4 font-semibold text-right">Rate</th>
                  <th className="py-2.5 pr-4 font-semibold text-right">GST</th>
                  <th className="py-2.5 font-semibold text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {inv.items.map((it, i) => (
                  <tr key={i} className="border-b border-slate-50">
                    <td className="py-3 pr-4 text-slate-800">{it.description}</td>
                    <td className="py-3 pr-4 font-mono text-slate-500">{it.hsn || "—"}</td>
                    <td className="py-3 pr-4 text-right font-mono text-slate-600">{it.qty}</td>
                    <td className="py-3 pr-4 text-right font-mono text-slate-600">{inr(it.rate)}</td>
                    <td className="py-3 pr-4 text-right font-mono text-slate-600">{it.gst_rate}%</td>
                    <td className="py-3 text-right font-mono font-semibold text-slate-900">{inr(it.qty * it.rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex justify-end">
            <dl className="w-full max-w-xs space-y-2 text-sm">
              <div className="flex justify-between"><dt className="text-slate-500">Subtotal</dt><dd className="font-mono text-slate-800">{inr(inv.subtotal)}</dd></div>
              {inv.discount_pct > 0 && <div className="flex justify-between"><dt className="text-slate-500">Discount</dt><dd className="font-mono text-emerald-600">-{inv.discount_pct}%</dd></div>}
              {inv.inter_state ? (
                <div className="flex justify-between"><dt className="text-slate-500">IGST</dt><dd className="font-mono text-slate-700">{inr(inv.igst)}</dd></div>
              ) : (
                <>
                  <div className="flex justify-between"><dt className="text-slate-500">CGST</dt><dd className="font-mono text-slate-700">{inr(inv.cgst)}</dd></div>
                  <div className="flex justify-between"><dt className="text-slate-500">SGST</dt><dd className="font-mono text-slate-700">{inr(inv.sgst)}</dd></div>
                </>
              )}
              <div className="border-t border-slate-200 pt-2.5 flex justify-between items-baseline">
                <dt className="font-semibold text-slate-900">Total</dt>
                <dd className="font-mono text-2xl font-extrabold text-[#5E35B1]" data-testid="invoice-detail-total">{inr(inv.total)}</dd>
              </div>
              {inv.paid_amount > 0 && (
                <>
                  <div className="flex justify-between"><dt className="text-slate-500">Paid</dt><dd className="font-mono text-emerald-600">{inr(inv.paid_amount)}</dd></div>
                  <div className="flex justify-between"><dt className="font-semibold text-slate-900">Balance due</dt><dd className="font-mono font-bold text-slate-900" data-testid="invoice-detail-balance">{inr(inv.balance_due)}</dd></div>
                </>
              )}
            </dl>
          </div>

          {(inv.notes || settings?.terms) && (
            <div className="mt-8 pt-6 border-t border-slate-100 text-sm text-slate-500 space-y-1">
              {inv.notes && <p><span className="font-semibold text-slate-700">Notes:</span> {inv.notes}</p>}
              {settings?.terms && <p><span className="font-semibold text-slate-700">Terms:</span> {settings.terms}</p>}
            </div>
          )}
        </div>

        <div className="xl:col-span-4 space-y-4 print-hidden">
          <div className="card-surface p-5 sm:p-6 text-center" data-testid="invoice-detail-upi-qr">
            <div className="flex items-center justify-center gap-2 mb-1">
              <QrCode className="w-4 h-4 text-[#0284C7]" />
              <h2 className="font-heading text-lg font-semibold text-slate-900">Pay via UPI</h2>
            </div>
            <p className="text-xs text-slate-400 mb-4">Scan with any UPI app to pay the balance.</p>
            {link ? (
              <>
                <div className="inline-block p-3 bg-white border border-slate-200 rounded-xl mb-3">
                  <QRCodeSVG value={link} size={180} level="M" />
                </div>
                <div className="font-mono text-xl font-extrabold text-slate-900 mb-4">{inr(inv.balance_due)}</div>
                <div className="flex flex-col gap-2">
                  <button onClick={copyLink} data-testid="invoice-detail-copy-upi-btn" className="inline-flex items-center justify-center gap-2 h-10 rounded-lg bg-[#0284C7] hover:bg-sky-700 text-white text-sm font-semibold transition-colors">
                    <Copy className="w-4 h-4" /> Copy UPI Link
                  </button>
                  <a href={link} data-testid="invoice-detail-open-upi-btn" className="inline-flex items-center justify-center gap-2 h-10 rounded-lg border border-sky-200 bg-sky-50 text-[#0284C7] text-sm font-semibold hover:bg-sky-100 transition-colors">
                    Open UPI App
                  </a>
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-400 py-4">
                Add your UPI ID in <Link to="/settings" className="text-[#5E35B1] font-semibold hover:underline">Settings</Link> to enable QR payments.
              </p>
            )}
          </div>

          <div className="card-surface p-5 sm:p-6" data-testid="invoice-detail-payments">
            <h2 className="font-heading text-lg font-semibold text-slate-900 mb-4">Payments</h2>
            {(!inv.payments || inv.payments.length === 0) ? (
              <p className="text-sm text-slate-400">No payments recorded yet.</p>
            ) : (
              <ul className="space-y-3">
                {inv.payments.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 text-sm" data-testid={`payment-row-${p.id}`}>
                    <div>
                      <div className="font-semibold text-slate-800 uppercase text-xs tracking-wide">{p.mode}</div>
                      <div className="text-xs text-slate-400">{fmtDate(p.date)}{p.reference ? ` · Ref ${p.reference}` : ""}</div>
                    </div>
                    <span className="font-mono font-semibold text-emerald-600">{inr(p.amount)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {payOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-slate-900/60" onClick={() => setPayOpen(false)} />
          <div className="relative card-surface w-full max-w-md p-6 animate-fade-up" data-testid="record-payment-modal">
            <h2 className="font-heading text-xl font-semibold text-slate-900 mb-1">Record payment</h2>
            <p className="text-sm text-slate-500 mb-5">Balance due: <span className="font-mono font-semibold text-slate-900">{inr(inv.balance_due)}</span></p>
            <div className="space-y-4">
              <div>
                <label className="field-label">Amount (₹)</label>
                <input data-testid="payment-amount-input" type="number" min="0" step="any" className="field-input font-mono" value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} />
              </div>
              <div>
                <label className="field-label">Mode</label>
                <select data-testid="payment-mode-select" className="field-input" value={pay.mode} onChange={(e) => setPay({ ...pay, mode: e.target.value })}>
                  {MODES.map((m) => <option key={m.v} value={m.v}>{m.label}</option>)}
                </select>
              </div>
              <div>
                <label className="field-label">Transaction reference</label>
                <input data-testid="payment-reference-input" className="field-input font-mono" placeholder="UPI UTR / cheque no. (optional)" value={pay.reference} onChange={(e) => setPay({ ...pay, reference: e.target.value })} />
              </div>
              <div>
                <label className="field-label">Note</label>
                <input data-testid="payment-note-input" className="field-input" placeholder="Optional" value={pay.note} onChange={(e) => setPay({ ...pay, note: e.target.value })} />
              </div>
              <div className="flex gap-3 pt-1">
                <button onClick={() => setPayOpen(false)} data-testid="payment-cancel-btn" className="flex-1 h-10 rounded-lg border border-slate-300 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-colors">
                  Cancel
                </button>
                <button onClick={recordPayment} disabled={saving} data-testid="payment-submit-btn" className="flex-1 h-10 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold transition-colors disabled:opacity-60">
                  {saving ? "Saving…" : "Record"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
