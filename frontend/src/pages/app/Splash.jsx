import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Wallet as WalletIcon, TrendingUp, Sparkles,
  ChevronRight, Plane, RotateCcw, FileBarChart, Gift,
} from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { CATEGORIES, catByKey } from '@/lib/categories';
import api from '@/lib/api';
import { VoiceExpense } from '@/components/VoiceExpense';
import { ReceiptScan } from '@/components/ReceiptScan';

const greet = () => {
  const h = new Date().getHours();
  if (h < 5) return 'Good night';
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  if (h < 21) return 'Good evening';
  return 'Good night';
};

const todayKey = () => new Date().toISOString().slice(0, 10);

export default function Splash() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [stats, setStats] = useState({ total: 0, today: 0, count: 0 });
  const [merchants, setMerchants] = useState([]);
  const isAdmin = user?.role === 'admin' && user?.company_id;

  useEffect(() => {
    if (isAdmin) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const [s, e, m] = await Promise.all([
          api.get('/expenses/stats'),
          api.get('/expenses'),
          api.get('/expenses/merchants/recent'),
        ]);
        if (cancelled) return;
        const expenses = e.data?.expenses || [];
        const tk = todayKey();
        const today = expenses
          .filter((x) => (x.created_at || '').slice(0, 10) === tk)
          .reduce((sum, x) => sum + Number(x.total || 0), 0);
        setStats({
          total: s.data?.total_expenses || 0,
          today,
          count: s.data?.expense_count || 0,
        });
        setMerchants(m.data?.merchants || []);
      } catch { /* ignore */ }
    })();
    return () => { cancelled = true; };
  }, [isAdmin]);

  const food = useMemo(() => catByKey('food'), []);
  const allCats = useMemo(() => CATEGORIES, []);
  const firstName = user?.name?.split(' ')[0] || 'there';

  // Corporate admins land on the Company Dashboard instead of the personal splash.
  // (Placed after hooks so hook order stays stable.)
  if (isAdmin) {
    return <Navigate to="/app/company" replace />;
  }

  const quickPay = (m) => {
    sessionStorage.setItem('bill4pe_draft', JSON.stringify({
      category: m.category,
      sub_category: m.sub_category,
      items: [{ name: `${(catByKey(m.category)?.label) || 'Expense'} (quick-pay)`, quantity: 1, unit_price: m.last_amount || 0 }],
      prefill_merchant: m,
    }));
    nav('/app/editor');
  };

  return (
    <div className="space-y-6">
      {/* ------- Greeting ------- */}
      <motion.div
        initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <div className="text-[11px] uppercase tracking-[0.3em] text-slate-400 font-bold">
          {greet()}
        </div>
        <h1 className="font-display text-3xl font-bold text-navy mt-1.5 tracking-tight">
          Hi, {firstName}.
        </h1>
      </motion.div>

      {/* ------- Compact wallet + stats card ------- */}
      <motion.div
        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
        className="rounded-2xl bg-white border border-soft p-4"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-[#050816] text-brand grid place-items-center shrink-0">
              <WalletIcon className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="text-[9px] uppercase tracking-[0.2em] text-slate-400 font-bold">Wallet</div>
              <div className="font-mono text-lg font-bold text-navy leading-tight" data-testid="splash-wallet-balance">
                ₹ {user?.wallet_balance?.toFixed(2) ?? '0.00'}
              </div>
            </div>
          </div>
          {user?.role === 'employee' ? (
            <div className="text-[10px] text-slate-400 max-w-[40%] text-right leading-tight">
              Company wallet handles billing
            </div>
          ) : (
            <button
              onClick={() => nav('/app/wallet')}
              data-testid="splash-recharge-btn"
              className="press-down text-xs font-semibold text-navy underline underline-offset-2 hover:text-[#152042] shrink-0"
            >
              + Recharge
            </button>
          )}
        </div>

        {/* compact 3-stat row */}
        <div className="mt-3 grid grid-cols-3 gap-2 pt-3 border-t border-soft">
          <div>
            <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold">Today</div>
            <div className="font-mono font-semibold text-sm text-navy mt-0.5" data-testid="splash-stat-today">
              ₹{stats.today.toFixed(0)}
            </div>
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold">All time</div>
            <div className="font-mono font-semibold text-sm text-navy mt-0.5" data-testid="splash-stat-total">
              ₹{stats.total.toFixed(0)}
            </div>
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold">Bills</div>
            <div className="font-mono font-semibold text-sm text-navy mt-0.5" data-testid="splash-stat-bills">
              {stats.count}
            </div>
          </div>
        </div>
      </motion.div>

      {/* ------- Receipt OCR scanner ------- */}
      <ReceiptScan />

      {/* ------- Voice expense entry (AI Whisper) ------- */}
      <VoiceExpense />

      {/* ------- Quick action chips ------- */}
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
        className="grid grid-cols-3 gap-2.5"
      >
        <button
          onClick={() => nav('/app/dashboard')}
          data-testid="splash-quick-dashboard"
          className="press-down flat-card p-3 flex flex-col items-start gap-1 hover:border-navy transition"
        >
          <TrendingUp className="w-4 h-4 text-navy" />
          <span className="text-[11px] font-semibold text-navy">Reports</span>
        </button>
        <button
          onClick={() => nav('/app/reports')}
          data-testid="splash-quick-reports"
          className="press-down flat-card p-3 flex flex-col items-start gap-1 hover:border-navy transition"
        >
          <FileBarChart className="w-4 h-4 text-navy" />
          <span className="text-[11px] font-semibold text-navy">Bundles</span>
        </button>
        <button
          onClick={() => nav('/app/trips')}
          data-testid="splash-quick-trips"
          className="press-down flat-card p-3 flex flex-col items-start gap-1 hover:border-navy transition"
        >
          <Plane className="w-4 h-4 text-navy" />
          <span className="text-[11px] font-semibold text-navy">Trips</span>
        </button>
      </motion.div>

      {/* ------- Recent merchants (quick re-pay) ------- */}
      {merchants.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.12 }}
        >
          <div className="flex items-center gap-1.5 mb-2 text-[11px] uppercase tracking-[0.25em] text-slate-400 font-bold">
            <RotateCcw className="w-3 h-3" /> Pay again
          </div>
          <div className="-mx-4 px-4 overflow-x-auto no-scrollbar">
            <div className="flex gap-2.5">
              {merchants.map((m) => (
                <button
                  key={m.merchant_name + (m.merchant_upi || '')}
                  onClick={() => quickPay(m)}
                  data-testid={`recent-merchant-${m.merchant_name}`}
                  className="press-down shrink-0 w-40 flat-card p-3 text-left hover:border-navy"
                >
                  <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold truncate">
                    {catByKey(m.category)?.label || m.category}
                  </div>
                  <div className="font-display font-bold text-navy text-sm truncate mt-1">
                    {m.merchant_name}
                  </div>
                  <div className="font-mono text-xs text-brand mt-1.5 font-semibold">
                    ₹ {m.last_amount.toFixed(0)}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </motion.div>
      )}

      {/* ------- Section header ------- */}
      <div className="flex items-end justify-between pt-1">
        <div>
          <div className="text-[11px] uppercase tracking-[0.3em] text-slate-400 font-bold">
            Pick a category
          </div>
          <h2 className="font-display text-xl font-bold text-navy mt-1.5">
            What did you spend on?
          </h2>
        </div>
        <div className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider font-bold text-navy bg-lime px-2 py-1 rounded-full">
          <Sparkles className="w-3 h-3" /> AI
        </div>
      </div>

      {/* ------- All categories grid (equal weight) ------- */}
      <motion.div
        initial="hidden" animate="show"
        variants={{ show: { transition: { staggerChildren: 0.025, delayChildren: 0.12 } } }}
        className="grid grid-cols-2 gap-3"
      >
        {allCats.map(({ key, label, icon: Icon, sub, tint, ink }) => (
          <motion.button
            key={key}
            variants={{
              hidden: { opacity: 0, y: 12 },
              show: { opacity: 1, y: 0 },
            }}
            whileHover={{ y: -2 }}
            onClick={() => nav(`/app/category/${key}`)}
            data-testid={`category-${key}-card`}
            className="press-down group flat-card p-3 text-left hover:border-navy transition-colors flex items-center gap-3"
          >
            <div
              className="w-12 h-12 rounded-full grid place-items-center shrink-0 ring-1 ring-black/[0.04] shadow-sm transition-transform group-hover:scale-105"
              style={{ backgroundColor: tint, color: ink }}
            >
              <Icon className="w-6 h-6" strokeWidth={1.9} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-display font-bold text-sm text-navy truncate">{label}</div>
              <div className="text-[10px] text-slate-400 font-medium mt-0.5">
                {sub.length} options
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-navy transition shrink-0" />
          </motion.button>
        ))}
      </motion.div>

      {/* ------- Refer & earn banner ------- */}
      <motion.button
        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.35 }}
        onClick={() => nav('/app/referrals')}
        data-testid="splash-refer-banner"
        className="press-down relative w-full overflow-hidden rounded-2xl bg-navy text-white p-4 text-left group"
      >
        <div
          className="absolute inset-0 opacity-50 pointer-events-none"
          style={{
            background:
              'radial-gradient(circle at 90% 30%, rgba(31,111,235,0.45), transparent 55%)',
          }}
        />
        <Gift className="absolute -right-3 -bottom-3 w-24 h-24 text-white/[0.06]" strokeWidth={1} />
        <div className="relative flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-brand text-white grid place-items-center shrink-0">
            <Gift className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-[0.25em] text-brand/90 font-bold">Refer & earn</div>
            <div className="font-display font-bold text-base mt-0.5 leading-tight">
              Invite a friend, both get ₹50
            </div>
          </div>
          <ChevronRight className="w-5 h-5 text-brand transition-transform group-hover:translate-x-1" />
        </div>
      </motion.button>

      {/* ------- Tip card (only if user has no bills yet) ------- */}
      {stats.count === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }}
          className="flat-card p-4 flex items-start gap-3 bg-[#F4F5F7] border-0"
        >
          <div className="w-8 h-8 rounded-full bg-navy text-lime grid place-items-center shrink-0">
            <Sparkles className="w-4 h-4" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-bold text-navy">Pro tip</div>
            <div className="text-xs text-slate-500 mt-0.5 leading-relaxed">
              Snap a clear photo of your bill — our AI auto-detects items, quantity and prices in seconds.
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}
