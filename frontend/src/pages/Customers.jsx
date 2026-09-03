import { useEffect, useMemo, useState } from "react";
import { Search, UserPlus, Users, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { API, fmtErr } from "@/lib/api";
import { inr } from "@/lib/format";

const EMPTY = { business_name: "", contact_person: "", phone: "", email: "", address: "", state: "", gstin: "" };

export default function Customers() {
  const [customers, setCustomers] = useState(null);
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(null); // null | {mode:'add'|'edit', form, id?}
  const [saving, setSaving] = useState(false);

  const load = () => API.get("/customers").then((r) => setCustomers(r.data)).catch(() => setCustomers([]));
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    if (!customers) return [];
    if (!search) return customers;
    const s = search.toLowerCase();
    return customers.filter((c) =>
      [c.business_name, c.contact_person, c.phone, c.email, c.gstin].some((v) => (v || "").toLowerCase().includes(s))
    );
  }, [customers, search]);

  const save = async () => {
    if (!modal.form.business_name.trim()) {
      toast.error("Business name is required");
      return;
    }
    setSaving(true);
    try {
      if (modal.mode === "add") {
        await API.post("/customers", modal.form);
        toast.success("Customer added");
      } else {
        await API.put(`/customers/${modal.id}`, modal.form);
        toast.success("Customer updated");
      }
      setModal(null);
      load();
    } catch (e) {
      toast.error(fmtErr(e));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (c) => {
    if (!window.confirm(`Delete ${c.business_name}?`)) return;
    try {
      await API.delete(`/customers/${c.id}`);
      toast.success("Customer deleted");
      load();
    } catch (e) {
      toast.error(fmtErr(e));
    }
  };

  const set = (k) => (e) => setModal({ ...modal, form: { ...modal.form, [k]: e.target.value } });

  return (
    <div data-testid="customers-page" className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl sm:text-4xl font-bold text-slate-900">Customers</h1>
          <p className="text-slate-500 text-sm mt-1">Your client directory with outstanding balances.</p>
        </div>
        <button
          data-testid="customers-add-customer-btn"
          onClick={() => setModal({ mode: "add", form: { ...EMPTY } })}
          className="inline-flex items-center gap-2 h-10 px-4 rounded-lg bg-[#5E35B1] hover:bg-[#512DA8] text-white text-sm font-semibold transition-colors shadow-[0_6px_18px_rgba(94,53,177,0.35)]"
        >
          <UserPlus className="w-4 h-4" /> Add Customer
        </button>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          data-testid="customers-search-input"
          className="field-input pl-9"
          placeholder="Search name, phone, GSTIN…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {!customers ? (
        <div className="text-slate-400 text-sm py-20 text-center">Loading customers…</div>
      ) : filtered.length === 0 ? (
        <div className="card-surface p-12 text-center" data-testid="customers-empty-state">
          <Users className="w-10 h-10 text-slate-300 mx-auto mb-4" />
          <p className="text-slate-500 text-sm mb-5">{customers.length === 0 ? "No customers yet — add your first client." : "Nothing matches this search."}</p>
          {customers.length === 0 && (
            <button
              data-testid="customers-empty-add-btn"
              onClick={() => setModal({ mode: "add", form: { ...EMPTY } })}
              className="inline-flex items-center gap-2 h-10 px-5 rounded-lg bg-[#5E35B1] hover:bg-[#512DA8] text-white text-sm font-semibold transition-colors"
            >
              <UserPlus className="w-4 h-4" /> Add First Customer
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 sm:gap-6">
          {filtered.map((c) => (
            <div key={c.id} data-testid={`customer-card-item-${c.id}`} className="card-surface p-5 sm:p-6 group">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-10 h-10 rounded-full bg-[#EDE7F6] text-[#5E35B1] flex items-center justify-center font-bold uppercase shrink-0">
                    {(c.business_name || "?")[0]}
                  </div>
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-900 truncate">{c.business_name}</div>
                    <div className="text-xs text-slate-500 truncate">{c.contact_person || c.phone || "—"}</div>
                  </div>
                </div>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button data-testid={`customer-edit-${c.id}`} onClick={() => setModal({ mode: "edit", id: c.id, form: { ...EMPTY, ...c } })} className="p-2 rounded-lg text-slate-400 hover:text-[#5E35B1] hover:bg-[#EDE7F6] transition-colors">
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button data-testid={`customer-delete-${c.id}`} onClick={() => remove(c)} className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div className="mt-4 space-y-1 text-xs text-slate-500">
                {c.email && <div className="truncate">{c.email}</div>}
                {c.gstin && <div className="font-mono">GSTIN: {c.gstin}</div>}
                {c.state && <div>{c.state}</div>}
              </div>
              <div className="mt-4 pt-4 border-t border-slate-100 flex items-center justify-between text-sm">
                <span className="text-slate-500">{c.invoice_count} invoice{c.invoice_count === 1 ? "" : "s"}</span>
                <span className={`font-mono font-semibold ${c.outstanding > 0 ? "text-amber-600" : "text-emerald-600"}`}>
                  {c.outstanding > 0 ? `${inr(c.outstanding)} due` : "No dues"}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-slate-900/60" onClick={() => setModal(null)} />
          <div className="relative card-surface w-full max-w-lg p-6 animate-fade-up max-h-[90vh] overflow-y-auto" data-testid="customer-modal">
            <h2 className="font-heading text-xl font-semibold text-slate-900 mb-5">
              {modal.mode === "add" ? "Add customer" : "Edit customer"}
            </h2>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <label className="field-label">Business name *</label>
                <input data-testid="customer-modal-name-input" className="field-input" value={modal.form.business_name} onChange={set("business_name")} />
              </div>
              <div>
                <label className="field-label">Contact person</label>
                <input data-testid="customer-modal-contact-input" className="field-input" value={modal.form.contact_person} onChange={set("contact_person")} />
              </div>
              <div>
                <label className="field-label">Phone</label>
                <input data-testid="customer-modal-phone-input" className="field-input" value={modal.form.phone} onChange={set("phone")} />
              </div>
              <div>
                <label className="field-label">Email</label>
                <input data-testid="customer-modal-email-input" type="email" className="field-input" value={modal.form.email} onChange={set("email")} />
              </div>
              <div>
                <label className="field-label">State</label>
                <input data-testid="customer-modal-state-input" className="field-input" placeholder="Maharashtra" value={modal.form.state} onChange={set("state")} />
              </div>
              <div className="sm:col-span-2">
                <label className="field-label">GSTIN</label>
                <input data-testid="customer-modal-gstin-input" className="field-input font-mono" placeholder="27ABCDE1234F1Z5" value={modal.form.gstin} onChange={set("gstin")} />
              </div>
              <div className="sm:col-span-2">
                <label className="field-label">Billing address</label>
                <textarea data-testid="customer-modal-address-input" className="field-input h-20 py-2 resize-none" value={modal.form.address} onChange={set("address")} />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setModal(null)} data-testid="customer-modal-cancel-btn" className="flex-1 h-10 rounded-lg border border-slate-300 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-colors">
                Cancel
              </button>
              <button onClick={save} disabled={saving} data-testid="customer-modal-save-btn" className="flex-1 h-10 rounded-lg bg-[#5E35B1] hover:bg-[#512DA8] text-white text-sm font-semibold transition-colors disabled:opacity-60">
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
