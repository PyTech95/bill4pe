import { useEffect, useState } from "react";
import { toast } from "sonner";
import { API, fmtErr } from "@/lib/api";

const EMPTY = {
  business_name: "", trade_name: "", gstin: "", state: "", address: "",
  upi_id: "", bank_account: "", bank_ifsc: "", bank_branch: "",
  invoice_prefix: "INV", terms: "",
};

export default function Settings() {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    API.get("/settings").then((r) => setForm({ ...EMPTY, ...r.data })).catch(() => setForm({ ...EMPTY }));
  }, []);

  if (!form) return <div className="text-slate-400 text-sm py-20 text-center">Loading settings…</div>;

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await API.put("/settings", form);
      setForm({ ...EMPTY, ...data });
      toast.success("Settings saved");
    } catch (e) {
      toast.error(fmtErr(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="settings-page" className="space-y-6 max-w-3xl">
      <div>
        <h1 className="font-heading text-3xl sm:text-4xl font-bold text-slate-900">Business Settings</h1>
        <p className="text-slate-500 text-sm mt-1">These details appear on every invoice and power UPI payments.</p>
      </div>

      <div className="card-surface p-5 sm:p-6 space-y-5">
        <h2 className="font-heading text-lg font-semibold text-slate-900">Business profile</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="field-label">Business name</label>
            <input data-testid="settings-business-name-input" className="field-input" placeholder="Acme Traders" value={form.business_name} onChange={set("business_name")} />
          </div>
          <div>
            <label className="field-label">Trade name</label>
            <input data-testid="settings-trade-name-input" className="field-input" value={form.trade_name} onChange={set("trade_name")} />
          </div>
          <div>
            <label className="field-label">GSTIN</label>
            <input data-testid="settings-gstin-input" className="field-input font-mono" placeholder="27ABCDE1234F1Z5" value={form.gstin} onChange={set("gstin")} />
          </div>
          <div>
            <label className="field-label">State</label>
            <input data-testid="settings-state-input" className="field-input" placeholder="Maharashtra" value={form.state} onChange={set("state")} />
          </div>
          <div className="sm:col-span-2">
            <label className="field-label">Address</label>
            <textarea data-testid="settings-address-input" className="field-input h-20 py-2 resize-none" value={form.address} onChange={set("address")} />
          </div>
        </div>
      </div>

      <div className="card-surface p-5 sm:p-6 space-y-5">
        <h2 className="font-heading text-lg font-semibold text-slate-900">Payments</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className="field-label">Primary UPI ID</label>
            <input data-testid="settings-upi-id-input" className="field-input font-mono" placeholder="business@okaxis" value={form.upi_id} onChange={set("upi_id")} />
            <p className="text-xs text-slate-400 mt-1.5">Used to generate UPI QR codes and payment links on invoices.</p>
          </div>
          <div>
            <label className="field-label">Bank account no.</label>
            <input data-testid="settings-bank-account-input" className="field-input font-mono" value={form.bank_account} onChange={set("bank_account")} />
          </div>
          <div>
            <label className="field-label">IFSC</label>
            <input data-testid="settings-bank-ifsc-input" className="field-input font-mono" value={form.bank_ifsc} onChange={set("bank_ifsc")} />
          </div>
          <div>
            <label className="field-label">Branch</label>
            <input data-testid="settings-bank-branch-input" className="field-input" value={form.bank_branch} onChange={set("bank_branch")} />
          </div>
        </div>
      </div>

      <div className="card-surface p-5 sm:p-6 space-y-5">
        <h2 className="font-heading text-lg font-semibold text-slate-900">Invoice defaults</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="field-label">Invoice prefix</label>
            <input data-testid="settings-invoice-prefix-input" className="field-input font-mono uppercase" placeholder="INV" value={form.invoice_prefix} onChange={set("invoice_prefix")} />
          </div>
          <div className="sm:col-span-2">
            <label className="field-label">Default terms</label>
            <textarea data-testid="settings-terms-input" className="field-input h-20 py-2 resize-none" value={form.terms} onChange={set("terms")} />
          </div>
        </div>
      </div>

      <button
        data-testid="settings-save-button"
        onClick={save}
        disabled={saving}
        className="h-11 px-8 rounded-lg bg-[#5E35B1] hover:bg-[#512DA8] text-white font-semibold text-sm transition-all shadow-[0_6px_18px_rgba(94,53,177,0.35)] disabled:opacity-60"
      >
        {saving ? "Saving…" : "Save Settings"}
      </button>
    </div>
  );
}
