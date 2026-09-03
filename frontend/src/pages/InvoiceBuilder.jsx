import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Plus, Trash2, ArrowLeft } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";
import { API, fmtErr } from "@/lib/api";
import { inr, todayISO, addDaysISO, upiLink, GST_SLABS, computeTotals } from "@/lib/format";

const EMPTY_ITEM = { description: "", hsn: "", qty: 1, rate: 0, gst_rate: 18 };

export default function InvoiceBuilder() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const [customers, setCustomers] = useState([]);
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState({
    customer_id: "", invoice_number: "", issue_date: todayISO(), due_date: addDaysISO(14),
    discount_pct: 0, inter_state: false, notes: "",
  });
  const [items, setItems] = useState([{ ...EMPTY_ITEM }]);
  const [saving, setSaving] = useState(false);
  const [showQuickAdd, setShowQuickAdd] = useState(false);
  const [quickCustomer, setQuickCustomer] = useState({ business_name: "", phone: "", gstin: "", state: "" });
  const [loaded, setLoaded] = useState(!isEdit);

  useEffect(() => {
    API.get("/customers").then((r) => setCustomers(r.data)).catch(() => {});
    API.get("/settings").then((r) => setSettings(r.data)).catch(() => {});
    if (isEdit) {
      API.get(`/invoices/${id}`)
        .then((r) => {
          const inv = r.data;
          setForm({
            customer_id: inv.customer_id, invoice_number: inv.invoice_number,
            issue_date: inv.issue_date, due_date: inv.due_date,
            discount_pct: inv.discount_pct, inter_state: inv.inter_state, notes: inv.notes || "",
          });
          setItems(inv.items.map((it) => ({ ...EMPTY_ITEM, ...it })));
          setLoaded(true);
        })
        .catch((e) => {
          toast.error(fmtErr(e));
          navigate("/invoices");
        });
    }
  }, [id, isEdit, navigate]);

  const selectedCustomer = customers.find((c) => c.id === form.customer_id);

  useEffect(() => {
    if (!isEdit && selectedCustomer && settings && selectedCustomer.state && settings.state) {
      setForm((f) => ({ ...f, inter_state: selectedCustomer.state.trim().toLowerCase() !== settings.state.trim().toLowerCase() }));
    }
  }, [form.customer_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const totals = useMemo(() => computeTotals(items, form.discount_pct, form.inter_state), [items, form.discount_pct, form.inter_state]);

  const setItem = (i, k, v) => setItems(items.map((it, idx) => (idx === i ? { ...it, [k]: v } : it)));

  const quickAddCustomer = async () => {
    try {
      const { data } = await API.post("/customers", quickCustomer);
      setCustomers([data, ...customers]);
      setForm({ ...form, customer_id: data.id });
      setShowQuickAdd(false);
      setQuickCustomer({ business_name: "", phone: "", gstin: "", state: "" });
      toast.success("Customer added");
    } catch (e) {
      toast.error(fmtErr(e));
    }
  };

  const save = async (send) => {
    if (!form.customer_id) {
      toast.error("Select a customer first");
      return;
    }
    if (!items.some((it) => it.description.trim())) {
      toast.error("Add at least one line item");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        discount_pct: Number(form.discount_pct) || 0,
        items: items.filter((it) => it.description.trim()).map((it) => ({ ...it, qty: Number(it.qty) || 0, rate: Number(it.rate) || 0, gst_rate: Number(it.gst_rate) || 0 })),
        status: send ? "sent" : "draft",
      };
      let invId = id;
      if (isEdit) {
        await API.put(`/invoices/${id}`, payload);
      } else {
        const { data } = await API.post("/invoices", payload);
        invId = data.id;
      }
      if (send && isEdit) await API.post(`/invoices/${invId}/send`).catch(() => {});
      toast.success(send ? "Invoice saved & marked sent" : "Invoice saved as draft");
      navigate(`/invoices/${invId}`);
    } catch (e) {
      toast.error(fmtErr(e));
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) return <div className="text-slate-400 text-sm py-20 text-center">Loading invoice…</div>;

  const link = settings?.upi_id
    ? upiLink({ upiId: settings.upi_id, name: settings.business_name, amount: totals.total, invoiceNumber: form.invoice_number || "DRAFT" })
    : null;

  return (
    <div data-testid="invoice-builder-page" className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/invoices" data-testid="invoice-builder-back-link" className="p-2 rounded-lg border border-slate-200 bg-white text-slate-500 hover:text-slate-900 transition-colors">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div>
          <h1 className="font-heading text-3xl sm:text-4xl font-bold text-slate-900">{isEdit ? "Edit Invoice" : "New Invoice"}</h1>
          <p className="text-slate-500 text-sm mt-1">GST auto-computed. UPI QR generated live.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 sm:gap-6 items-start">
        <div className="xl:col-span-8 space-y-4 sm:space-y-6">
          <div className="card-surface p-5 sm:p-6 space-y-5">
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="field-label !mb-0">Customer</label>
                  <button type="button" data-testid="invoice-builder-quick-add-customer" onClick={() => setShowQuickAdd(!showQuickAdd)} className="text-xs font-semibold text-[#5E35B1] hover:underline">
                    + Quick add
                  </button>
                </div>
                <select
                  data-testid="invoice-builder-client-select"
                  className="field-input"
                  value={form.customer_id}
                  onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
                >
                  <option value="">Select customer…</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>{c.business_name}</option>
                  ))}
                </select>
                {showQuickAdd && (
                  <div className="mt-3 p-4 rounded-lg border border-[#5E35B1]/30 bg-[#EDE7F6]/40 space-y-3" data-testid="invoice-builder-quick-add-form">
                    <input className="field-input" placeholder="Business name *" data-testid="quick-add-name-input" value={quickCustomer.business_name} onChange={(e) => setQuickCustomer({ ...quickCustomer, business_name: e.target.value })} />
                    <div className="grid grid-cols-2 gap-3">
                      <input className="field-input" placeholder="Phone" data-testid="quick-add-phone-input" value={quickCustomer.phone} onChange={(e) => setQuickCustomer({ ...quickCustomer, phone: e.target.value })} />
                      <input className="field-input" placeholder="State" data-testid="quick-add-state-input" value={quickCustomer.state} onChange={(e) => setQuickCustomer({ ...quickCustomer, state: e.target.value })} />
                    </div>
                    <input className="field-input font-mono" placeholder="GSTIN (optional)" data-testid="quick-add-gstin-input" value={quickCustomer.gstin} onChange={(e) => setQuickCustomer({ ...quickCustomer, gstin: e.target.value })} />
                    <button type="button" data-testid="quick-add-save-button" onClick={quickAddCustomer} className="h-9 px-4 rounded-lg bg-[#5E35B1] text-white text-xs font-semibold hover:bg-[#512DA8] transition-colors">
                      Add & Select
                    </button>
                  </div>
                )}
              </div>
              <div>
                <label className="field-label">Invoice number</label>
                <input
                  data-testid="invoice-builder-number-input"
                  className="field-input font-mono"
                  placeholder="Auto-generated"
                  value={form.invoice_number}
                  onChange={(e) => setForm({ ...form, invoice_number: e.target.value })}
                />
              </div>
              <div>
                <label className="field-label">Issue date</label>
                <input data-testid="invoice-builder-issue-date" type="date" className="field-input" value={form.issue_date} onChange={(e) => setForm({ ...form, issue_date: e.target.value })} />
              </div>
              <div>
                <label className="field-label">Due date</label>
                <input data-testid="invoice-builder-due-date" type="date" className="field-input" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
              </div>
            </div>
            <label className="flex items-center gap-2.5 text-sm text-slate-600 cursor-pointer select-none">
              <input
                type="checkbox"
                data-testid="invoice-builder-interstate-toggle"
                checked={form.inter_state}
                onChange={(e) => setForm({ ...form, inter_state: e.target.checked })}
                className="w-4 h-4 rounded border-slate-300 text-[#5E35B1] focus:ring-[#5E35B1]"
              />
              Inter-state supply (charge IGST instead of CGST + SGST)
            </label>
          </div>

          <div className="card-surface p-5 sm:p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-heading text-lg font-semibold text-slate-900">Line items</h2>
              <button
                type="button"
                data-testid="invoice-builder-add-item-button"
                onClick={() => setItems([...items, { ...EMPTY_ITEM }])}
                className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg border border-[#5E35B1]/40 text-[#5E35B1] text-xs font-semibold hover:bg-[#EDE7F6] transition-colors"
              >
                <Plus className="w-3.5 h-3.5" /> Add item
              </button>
            </div>
            <div className="space-y-3">
              <div className="hidden sm:grid grid-cols-12 gap-3 text-[11px] uppercase tracking-[0.14em] text-slate-400 font-semibold px-1">
                <div className="col-span-4">Description</div>
                <div className="col-span-2">HSN/SAC</div>
                <div className="col-span-1">Qty</div>
                <div className="col-span-2">Rate (₹)</div>
                <div className="col-span-2">GST %</div>
                <div className="col-span-1"></div>
              </div>
              {items.map((it, i) => (
                <div key={i} data-testid={`invoice-builder-item-row-${i}`} className="grid grid-cols-2 sm:grid-cols-12 gap-3 items-center">
                  <input data-testid={`invoice-builder-item-desc-${i}`} className="field-input col-span-2 sm:col-span-4" placeholder="Consulting services" value={it.description} onChange={(e) => setItem(i, "description", e.target.value)} />
                  <input data-testid={`invoice-builder-item-hsn-${i}`} className="field-input sm:col-span-2 font-mono" placeholder="9983" value={it.hsn} onChange={(e) => setItem(i, "hsn", e.target.value)} />
                  <input data-testid={`invoice-builder-item-qty-${i}`} type="number" min="0" step="any" className="field-input sm:col-span-1" value={it.qty} onChange={(e) => setItem(i, "qty", e.target.value)} />
                  <input data-testid={`invoice-builder-item-rate-${i}`} type="number" min="0" step="any" className="field-input sm:col-span-2" value={it.rate} onChange={(e) => setItem(i, "rate", e.target.value)} />
                  <select data-testid={`invoice-builder-item-gst-${i}`} className="field-input sm:col-span-2" value={it.gst_rate} onChange={(e) => setItem(i, "gst_rate", e.target.value)}>
                    {GST_SLABS.map((s) => (
                      <option key={s} value={s}>{s}%</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    data-testid={`invoice-builder-item-remove-${i}`}
                    onClick={() => setItems(items.length > 1 ? items.filter((_, idx) => idx !== i) : items)}
                    className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors justify-self-end sm:col-span-1"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
            <div className="grid sm:grid-cols-2 gap-4 mt-6">
              <div>
                <label className="field-label">Discount %</label>
                <input data-testid="invoice-builder-discount-input" type="number" min="0" max="100" step="any" className="field-input" value={form.discount_pct} onChange={(e) => setForm({ ...form, discount_pct: e.target.value })} />
              </div>
              <div>
                <label className="field-label">Notes</label>
                <input data-testid="invoice-builder-notes-input" className="field-input" placeholder="Thanks for your business!" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              </div>
            </div>
          </div>
        </div>

        <div className="xl:col-span-4 xl:sticky xl:top-8 space-y-4">
          <div className="card-surface p-5 sm:p-6" data-testid="invoice-builder-summary">
            <h2 className="font-heading text-lg font-semibold text-slate-900 mb-4">Summary</h2>
            <dl className="space-y-2.5 text-sm">
              <div className="flex justify-between"><dt className="text-slate-500">Subtotal</dt><dd className="font-mono font-semibold text-slate-900">{inr(totals.subtotal)}</dd></div>
              {Number(form.discount_pct) > 0 && (
                <div className="flex justify-between"><dt className="text-slate-500">Discount</dt><dd className="font-mono text-emerald-600">-{form.discount_pct}%</dd></div>
              )}
              {form.inter_state ? (
                <div className="flex justify-between"><dt className="text-slate-500">IGST</dt><dd className="font-mono text-slate-700">{inr(totals.igst)}</dd></div>
              ) : (
                <>
                  <div className="flex justify-between"><dt className="text-slate-500">CGST</dt><dd className="font-mono text-slate-700">{inr(totals.cgst)}</dd></div>
                  <div className="flex justify-between"><dt className="text-slate-500">SGST</dt><dd className="font-mono text-slate-700">{inr(totals.sgst)}</dd></div>
                </>
              )}
              <div className="border-t border-slate-100 pt-3 flex justify-between items-baseline">
                <dt className="font-semibold text-slate-900">Grand total</dt>
                <dd data-testid="invoice-builder-grand-total" className="font-mono text-2xl font-extrabold text-[#5E35B1]">{inr(totals.total)}</dd>
              </div>
            </dl>
          </div>

          <div className="card-surface p-5 sm:p-6 text-center" data-testid="invoice-builder-upi-preview">
            <h2 className="font-heading text-lg font-semibold text-slate-900 mb-1">UPI payment QR</h2>
            <p className="text-xs text-slate-400 mb-4">Updates live as you build the invoice.</p>
            {link ? (
              <div className="inline-block p-3 bg-white border border-slate-200 rounded-xl">
                <QRCodeSVG value={link} size={160} level="M" data-testid="invoice-builder-qr-code" />
              </div>
            ) : (
              <p className="text-sm text-slate-400 py-6">
                Add your UPI ID in <Link to="/settings" className="text-[#5E35B1] font-semibold hover:underline">Settings</Link> to enable QR payments.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-3">
            <button
              data-testid="invoice-builder-save-and-send-button"
              onClick={() => save(true)}
              disabled={saving}
              className="h-11 rounded-lg bg-[#5E35B1] hover:bg-[#512DA8] text-white font-semibold text-sm transition-all shadow-[0_6px_18px_rgba(94,53,177,0.35)] disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save & Mark Sent"}
            </button>
            <button
              data-testid="invoice-builder-save-button"
              onClick={() => save(false)}
              disabled={saving}
              className="h-11 rounded-lg border border-slate-300 bg-white text-slate-700 font-semibold text-sm hover:border-[#5E35B1] hover:text-[#5E35B1] transition-colors disabled:opacity-60"
            >
              Save as Draft
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
