import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { FilePlus2, Search, FileText } from "lucide-react";
import { API } from "@/lib/api";
import { inr, fmtDate } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";

const TABS = ["all", "pending", "paid", "overdue", "draft"];

export default function Invoices() {
  const [invoices, setInvoices] = useState(null);
  const [tab, setTab] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    API.get("/invoices").then((r) => setInvoices(r.data)).catch(() => setInvoices([]));
  }, []);

  const filtered = useMemo(() => {
    if (!invoices) return [];
    return invoices.filter((i) => {
      if (tab !== "all" && i.status !== tab) return false;
      if (search) {
        const s = search.toLowerCase();
        return i.invoice_number.toLowerCase().includes(s) || (i.customer_name || "").toLowerCase().includes(s);
      }
      return true;
    });
  }, [invoices, tab, search]);

  return (
    <div data-testid="invoices-page" className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl sm:text-4xl font-bold text-slate-900">Invoices</h1>
          <p className="text-slate-500 text-sm mt-1">Track, send and collect on every bill.</p>
        </div>
        <Link
          to="/invoices/new"
          data-testid="invoices-new-invoice-button"
          className="inline-flex items-center gap-2 h-10 px-4 rounded-lg bg-[#5E35B1] hover:bg-[#512DA8] text-white text-sm font-semibold transition-colors shadow-[0_6px_18px_rgba(94,53,177,0.35)]"
        >
          <FilePlus2 className="w-4 h-4" /> New Invoice
        </Link>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            data-testid="invoices-search-input"
            className="field-input pl-9"
            placeholder="Search invoice # or customer…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-1 bg-white border border-slate-200 rounded-lg p-1" data-testid="invoices-status-tabs">
          {TABS.map((t) => (
            <button
              key={t}
              data-testid={`invoices-tab-${t}`}
              onClick={() => setTab(t)}
              className={`px-3.5 h-8 rounded-md text-xs font-semibold capitalize transition-colors ${
                tab === t ? "bg-[#5E35B1] text-white" : "text-slate-500 hover:text-slate-900"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {!invoices ? (
        <div className="text-slate-400 text-sm py-20 text-center">Loading invoices…</div>
      ) : filtered.length === 0 ? (
        <div className="card-surface p-12 text-center" data-testid="invoices-empty-state">
          <FileText className="w-10 h-10 text-slate-300 mx-auto mb-4" />
          <p className="text-slate-500 text-sm mb-5">
            {invoices.length === 0 ? "No invoices yet. Create your first one now." : "Nothing matches this filter."}
          </p>
          {invoices.length === 0 && (
            <Link
              to="/invoices/new"
              data-testid="invoices-empty-create-button"
              className="inline-flex items-center gap-2 h-10 px-5 rounded-lg bg-[#5E35B1] hover:bg-[#512DA8] text-white text-sm font-semibold transition-colors"
            >
              <FilePlus2 className="w-4 h-4" /> Create First Invoice
            </Link>
          )}
        </div>
      ) : (
        <div className="card-surface overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="invoices-table">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-[0.14em] text-slate-400 border-b border-slate-100 bg-slate-50/50">
                  <th className="px-5 sm:px-6 py-3.5 font-semibold">Invoice</th>
                  <th className="px-4 py-3.5 font-semibold">Customer</th>
                  <th className="px-4 py-3.5 font-semibold">Issued</th>
                  <th className="px-4 py-3.5 font-semibold">Due</th>
                  <th className="px-4 py-3.5 font-semibold text-right">Total</th>
                  <th className="px-4 py-3.5 font-semibold text-right">Balance</th>
                  <th className="px-5 sm:px-6 py-3.5 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((inv) => (
                  <tr key={inv.id} data-testid={`invoice-row-item-${inv.id}`} className="border-b border-slate-50 hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 sm:px-6 py-4">
                      <Link to={`/invoices/${inv.id}`} className="font-mono font-semibold text-[#5E35B1] hover:underline">
                        {inv.invoice_number}
                      </Link>
                    </td>
                    <td className="px-4 py-4 text-slate-700">{inv.customer_name}</td>
                    <td className="px-4 py-4 text-slate-500">{fmtDate(inv.issue_date)}</td>
                    <td className="px-4 py-4 text-slate-500">{fmtDate(inv.due_date)}</td>
                    <td className="px-4 py-4 text-right font-mono font-semibold text-slate-900">{inr(inv.total)}</td>
                    <td className="px-4 py-4 text-right font-mono text-slate-600">{inr(inv.balance_due)}</td>
                    <td className="px-5 sm:px-6 py-4"><StatusBadge status={inv.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
