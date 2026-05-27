import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CATEGORIES, catByKey } from '@/lib/categories';
import { Filter, FileText, ChevronRight, TrendingUp, Download, Plane } from 'lucide-react';
import api, { API } from '@/lib/api';
import { useAuth } from '@/lib/auth';

const filters = [
  { label: 'All', days: null },
  { label: '7 days', days: 7 },
  { label: '30 days', days: 30 },
  { label: '90 days', days: 90 },
];

export default function Dashboard() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [expenses, setExpenses] = useState([]);
  const [stats, setStats] = useState({ total_expenses: 0, expense_count: 0, by_category: [] });
  const [days, setDays] = useState(null);
  const [cat, setCat] = useState(null);

  const load = async () => {
    const params = {};
    if (days) params.days = days;
    if (cat) params.category = cat;
    const [e, s] = await Promise.all([
      api.get('/expenses', { params }),
      api.get('/expenses/stats'),
    ]);
    setExpenses(e.data?.expenses || []);
    setStats(s.data || stats);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [days, cat]);

  const csvUrl = () => {
    const token = localStorage.getItem('bill4pe_token');
    const params = new URLSearchParams({ token: token || '' });
    if (days) params.set('days', days);
    if (cat) params.set('category', cat);
    return `${API}/expenses/export.csv?${params.toString()}`;
  };

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Overview</div>
          <h1 className="font-display text-2xl font-bold text-navy mt-1">Dashboard</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => nav('/app/trips')}
            data-testid="dashboard-trips-btn"
            className="press-down inline-flex items-center gap-1.5 h-9 px-3 rounded-full bg-[#0A1128]/5 text-navy text-xs font-semibold hover:bg-[#0A1128]/10"
            title="Trip history"
          >
            <Plane className="w-3.5 h-3.5" /> Trips
          </button>
          <a
            href={csvUrl()} target="_blank" rel="noopener noreferrer"
            data-testid="dashboard-csv-btn"
            className="press-down inline-flex items-center gap-1.5 h-9 px-3 rounded-full bg-navy text-white text-xs font-semibold hover:bg-[#152042]"
            title="Export as CSV"
          >
            <Download className="w-3.5 h-3.5" /> CSV
          </a>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="bg-navy text-white rounded-2xl p-5">
          <div className="text-[10px] uppercase tracking-wider text-lime/80">Total spent</div>
          <div className="font-mono text-2xl font-bold mt-1.5" data-testid="stat-total">₹ {stats.total_expenses.toFixed(2)}</div>
        </div>
        <div className="flat-card p-5">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Bills</div>
          <div className="font-mono text-2xl font-bold text-navy mt-1.5" data-testid="stat-count">{stats.expense_count}</div>
        </div>
      </div>

      {/* Category filter pills */}
      <div className="-mx-4 px-4 overflow-x-auto no-scrollbar">
        <div className="flex gap-2 w-max">
          <button
            onClick={() => setCat(null)}
            className={`press-down px-4 py-2 rounded-full text-xs font-semibold whitespace-nowrap ${cat === null ? 'bg-navy text-white' : 'bg-[#0A1128]/5 text-navy'}`}
            data-testid="filter-cat-all"
          >All</button>
          {CATEGORIES.map((c) => (
            <button
              key={c.key}
              onClick={() => setCat(c.key)}
              className={`press-down px-4 py-2 rounded-full text-xs font-semibold whitespace-nowrap ${cat === c.key ? 'bg-navy text-white' : 'bg-[#0A1128]/5 text-navy'}`}
              data-testid={`filter-cat-${c.key}`}
            >{c.label}</button>
          ))}
        </div>
      </div>

      {/* Date filter */}
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Filter className="w-3.5 h-3.5" />
        {filters.map((f) => (
          <button
            key={f.label}
            onClick={() => setDays(f.days)}
            className={`press-down px-3 py-1 rounded-full font-semibold ${days === f.days ? 'bg-navy text-white' : ''}`}
            data-testid={`filter-days-${f.label.replace(/\s/g, '')}`}
          >{f.label}</button>
        ))}
      </div>

      {stats.by_category.length > 0 && (
        <div className="flat-card p-5">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-400 font-semibold">
            <TrendingUp className="w-3.5 h-3.5" />By category
          </div>
          <div className="mt-3 space-y-2">
            {stats.by_category.map((b) => {
              const c = catByKey(b.category);
              const Icon = c?.icon || FileText;
              const pct = stats.total_expenses ? (b.amount / stats.total_expenses) * 100 : 0;
              return (
                <div key={b.category}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2 text-navy">
                      <Icon className="w-4 h-4" /> {c?.label || b.category}
                    </span>
                    <span className="font-mono text-navy">₹ {b.amount.toFixed(2)}</span>
                  </div>
                  <div className="h-1.5 bg-[#0A1128]/5 rounded-full mt-1 overflow-hidden">
                    <div className="h-full bg-navy" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div>
        <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Recent bills</div>
        <div className="mt-3 space-y-2">
          {expenses.length === 0 && (
            <div className="flat-card p-8 text-center text-slate-400 text-sm">
              No expenses yet. Tap a category to begin.
            </div>
          )}
          {expenses.map((e) => {
            const c = catByKey(e.category);
            const Icon = c?.icon || FileText;
            return (
              <button
                key={e.id}
                onClick={() => nav(`/app/bill/${e.id}`)}
                data-testid={`expense-row-${e.id}`}
                className="press-down w-full flat-card p-4 flex items-center gap-3 text-left hover:border-navy"
              >
                <div className="w-10 h-10 rounded-xl bg-navy text-lime grid place-items-center shrink-0">
                  <Icon className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-navy truncate">
                    {e.payment?.merchant_name || (c?.label + ' expense')}
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                    {e.created_at?.slice(0, 10)} · {(c?.label || e.category)}{e.sub_category ? ' / ' + e.sub_category : ''}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-mono font-bold text-navy">₹ {Number(e.total).toFixed(2)}</div>
                  {e.bill_generated && <div className="text-[9px] mt-0.5 text-emerald-600 font-semibold uppercase tracking-wider">Bill</div>}
                </div>
                <ChevronRight className="w-4 h-4 text-slate-300 ml-1" />
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
