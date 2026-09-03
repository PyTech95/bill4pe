import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { FilePlus2, UserPlus, ArrowUpRight, Wallet, Clock, AlertTriangle, Receipt } from "lucide-react";
import { API } from "@/lib/api";
import { inr, fmtDate } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";

function KpiCard({ label, value, icon: Icon, tone, testid }) {
  return (
    <div className="card-surface p-5 sm:p-6 animate-fade-up" data-testid={testid}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold tracking-[0.18em] uppercase text-slate-500">{label}</span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${tone}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div className="mt-3 font-mono text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">{inr(value)}</div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    API.get("/dashboard/stats").then((r) => setStats(r.data)).catch(() => setStats({}));
  }, []);

  if (!stats) {
    return <div data-testid="dashboard-loading" className="text-slate-400 text-sm py-20 text-center">Loading dashboard…</div>;
  }

  return (
    <div data-testid="dashboard-page" className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl sm:text-4xl font-bold text-slate-900">Dashboard</h1>
          <p className="text-slate-500 text-sm mt-1">Your business at a glance.</p>
        </div>
        <div className="flex gap-3">
          <Link
            to="/customers"
            data-testid="dashboard-add-customer-button"
            className="inline-flex items-center gap-2 h-10 px-4 rounded-lg border border-slate-300 bg-white text-sm font-semibold text-slate-700 hover:border-[#5E35B1] hover:text-[#5E35B1] transition-colors"
          >
            <UserPlus className="w-4 h-4" /> Add Customer
          </Link>
          <Link
            to="/invoices/new"
            data-testid="dashboard-create-invoice-button"
            className="inline-flex items-center gap-2 h-10 px-4 rounded-lg bg-[#5E35B1] hover:bg-[#512DA8] text-white text-sm font-semibold transition-colors shadow-[0_6px_18px_rgba(94,53,177,0.35)]"
          >
            <FilePlus2 className="w-4 h-4" /> New Invoice
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 sm:gap-6">
        <KpiCard label="Total Invoiced" value={stats.total_invoiced} icon={Receipt} tone="bg-[#EDE7F6] text-[#5E35B1]" testid="dashboard-kpi-total-revenue" />
        <KpiCard label="Collected" value={stats.collected} icon={Wallet} tone="bg-emerald-50 text-emerald-600" testid="dashboard-kpi-paid-amount" />
        <KpiCard label="Pending Dues" value={stats.pending} icon={Clock} tone="bg-amber-50 text-amber-600" testid="dashboard-kpi-pending-amount" />
        <KpiCard label="Overdue" value={stats.overdue} icon={AlertTriangle} tone="bg-rose-50 text-rose-600" testid="dashboard-kpi-overdue-amount" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 sm:gap-6">
        <div className="xl:col-span-8 card-surface p-5 sm:p-6" data-testid="dashboard-revenue-chart">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-heading text-lg font-semibold text-slate-900">Invoiced — last 6 months</h2>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={stats.monthly || []} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
                <defs>
                  <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#5E35B1" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#5E35B1" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 12, fill: "#64748B" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 12, fill: "#64748B" }} axisLine={false} tickLine={false} tickFormatter={(v) => (v >= 100000 ? `${v / 100000}L` : v >= 1000 ? `${v / 1000}k` : v)} />
                <Tooltip formatter={(v) => inr(v)} contentStyle={{ borderRadius: 12, border: "1px solid #E2E8F0", fontSize: 13 }} />
                <Area type="monotone" dataKey="total" stroke="#5E35B1" strokeWidth={2.5} fill="url(#rev)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="xl:col-span-4 card-surface p-5 sm:p-6" data-testid="dashboard-top-customers">
          <h2 className="font-heading text-lg font-semibold text-slate-900 mb-4">Top customers</h2>
          {(!stats.top_customers || stats.top_customers.length === 0) && (
            <p className="text-sm text-slate-400">No billing yet. Create your first invoice to see leaders here.</p>
          )}
          <ul className="space-y-3">
            {(stats.top_customers || []).map((c, i) => (
              <li key={i} className="flex items-center justify-between gap-3" data-testid={`dashboard-top-customer-${i}`}>
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-full bg-[#EDE7F6] text-[#5E35B1] flex items-center justify-center text-xs font-bold uppercase">
                    {(c.name || "?")[0]}
                  </div>
                  <span className="text-sm font-medium text-slate-800 truncate">{c.name}</span>
                </div>
                <span className="font-mono text-sm font-semibold text-slate-900">{inr(c.total)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="card-surface overflow-hidden">
        <div className="flex items-center justify-between px-5 sm:px-6 py-4 border-b border-slate-100">
          <h2 className="font-heading text-lg font-semibold text-slate-900">Recent invoices</h2>
          <Link to="/invoices" data-testid="dashboard-view-all-invoices-link" className="inline-flex items-center gap-1 text-sm font-semibold text-[#5E35B1] hover:underline">
            View all <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>
        {(!stats.recent_invoices || stats.recent_invoices.length === 0) ? (
          <div className="p-10 text-center" data-testid="dashboard-empty-state">
            <p className="text-slate-400 text-sm mb-4">No invoices yet — issue your first bill in under a minute.</p>
            <Link
              to="/invoices/new"
              data-testid="dashboard-empty-create-invoice-button"
              className="inline-flex items-center gap-2 h-10 px-5 rounded-lg bg-[#5E35B1] hover:bg-[#512DA8] text-white text-sm font-semibold transition-colors"
            >
              <FilePlus2 className="w-4 h-4" /> Create First Invoice
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="dashboard-recent-invoices-table">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-[0.14em] text-slate-400 border-b border-slate-100">
                  <th className="px-5 sm:px-6 py-3 font-semibold">Invoice</th>
                  <th className="px-4 py-3 font-semibold">Customer</th>
                  <th className="px-4 py-3 font-semibold">Due</th>
                  <th className="px-4 py-3 font-semibold text-right">Amount</th>
                  <th className="px-5 sm:px-6 py-3 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {stats.recent_invoices.map((inv) => (
                  <tr key={inv.id} className="border-b border-slate-50 hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 sm:px-6 py-3.5">
                      <Link to={`/invoices/${inv.id}`} className="font-mono font-semibold text-[#5E35B1] hover:underline">
                        {inv.invoice_number}
                      </Link>
                    </td>
                    <td className="px-4 py-3.5 text-slate-700">{inv.customer_name}</td>
                    <td className="px-4 py-3.5 text-slate-500">{fmtDate(inv.due_date)}</td>
                    <td className="px-4 py-3.5 text-right font-mono font-semibold text-slate-900">{inr(inv.total)}</td>
                    <td className="px-5 sm:px-6 py-3.5"><StatusBadge status={inv.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
