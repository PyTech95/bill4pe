import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Wallet as WalletIcon, ArrowRight, TrendingUp, Receipt, Sparkles,
  ChevronRight, Camera, Plane,
} from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { CATEGORIES, catByKey } from '@/lib/categories';
import api from '@/lib/api';

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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, e] = await Promise.all([
          api.get('/expenses/stats'),
          api.get('/expenses'),
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
      } catch { /* ignore */ }
    })();
    return () => { cancelled = true; };
  }, []);

  const food = useMemo(() => catByKey('food'), []);
  const otherCats = useMemo(() => CATEGORIES.filter((c) => c.key !== 'food'), []);
  const firstName = user?.name?.split(' ')[0] || 'there';

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

      {/* ------- Hero wallet card with 3-stat dashboard ------- */}
      <motion.div
        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
        className="relative overflow-hidden rounded-3xl bg-navy text-white p-5"
      >
        {/* decorative mesh */}
        <div
          className="absolute inset-0 opacity-40 pointer-events-none"
          style={{
            background:
              'radial-gradient(circle at 95% 5%, rgba(212,255,0,0.30) 0%, transparent 38%),' +
              'radial-gradient(circle at 5% 95%, rgba(212,255,0,0.10) 0%, transparent 40%)',
          }}
        />
        {/* tiny dot grid */}
        <div
          className="absolute inset-0 opacity-[0.06] pointer-events-none"
          style={{
            backgroundImage: 'radial-gradient(#fff 1px, transparent 1px)',
            backgroundSize: '14px 14px',
          }}
        />

        <div className="relative">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.3em] text-lime/80 font-bold flex items-center gap-1.5">
                <WalletIcon className="w-3 h-3" /> Wallet
              </div>
              <div className="font-mono text-3xl font-bold mt-2" data-testid="splash-wallet-balance">
                ₹ {user?.wallet_balance?.toFixed(2) ?? '0.00'}
              </div>
            </div>
            <button
              onClick={() => nav('/app/wallet')}
              data-testid="splash-recharge-btn"
              className="press-down inline-flex items-center gap-1 bg-lime text-navy text-xs font-bold px-3 py-2 rounded-full hover:bg-[#BCE300]"
            >
              + Recharge
            </button>
          </div>

          {/* 3-stat row */}
          <div className="mt-6 grid grid-cols-3 gap-3 pt-5 border-t border-white/10">
            <div>
              <div className="text-[9px] uppercase tracking-wider text-white/40 font-semibold">Today</div>
              <div className="font-mono font-bold text-base mt-1.5" data-testid="splash-stat-today">
                ₹{stats.today.toFixed(0)}
              </div>
            </div>
            <div className="border-l border-white/10 pl-3">
              <div className="text-[9px] uppercase tracking-wider text-white/40 font-semibold">All time</div>
              <div className="font-mono font-bold text-base mt-1.5" data-testid="splash-stat-total">
                ₹{stats.total.toFixed(0)}
              </div>
            </div>
            <div className="border-l border-white/10 pl-3">
              <div className="text-[9px] uppercase tracking-wider text-white/40 font-semibold">Bills</div>
              <div className="font-mono font-bold text-base mt-1.5" data-testid="splash-stat-bills">
                {stats.count}
              </div>
            </div>
          </div>
        </div>
      </motion.div>

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
          onClick={() => nav('/app/trips')}
          data-testid="splash-quick-trips"
          className="press-down flat-card p-3 flex flex-col items-start gap-1 hover:border-navy transition"
        >
          <Plane className="w-4 h-4 text-navy" />
          <span className="text-[11px] font-semibold text-navy">Trips</span>
        </button>
        <button
          onClick={() => nav('/app/dashboard')}
          data-testid="splash-quick-bills"
          className="press-down flat-card p-3 flex flex-col items-start gap-1 hover:border-navy transition"
        >
          <Receipt className="w-4 h-4 text-navy" />
          <span className="text-[11px] font-semibold text-navy">All Bills</span>
        </button>
      </motion.div>

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

      {/* ------- Featured Food card (full width) ------- */}
      <motion.button
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.12 }}
        onClick={() => nav(`/app/category/${food.key}`)}
        data-testid={`category-${food.key}-card`}
        whileHover={{ y: -2 }}
        className="press-down relative w-full overflow-hidden rounded-3xl bg-navy text-white p-5 text-left group"
      >
        {/* halo */}
        <div
          className="absolute inset-0 opacity-50 pointer-events-none"
          style={{
            background:
              'radial-gradient(circle at 85% 30%, rgba(212,255,0,0.25), transparent 45%)',
          }}
        />
        {/* decorative camera icon */}
        <Camera className="absolute -right-6 -bottom-6 w-44 h-44 text-white/[0.04]" strokeWidth={1} />

        <div className="relative flex items-start gap-4">
          <div className="w-14 h-14 rounded-2xl bg-lime text-navy grid place-items-center shrink-0 shadow-lg shadow-lime/20">
            <food.icon className="w-7 h-7" strokeWidth={1.8} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-[0.25em] text-lime/80 font-bold">
              Most popular
            </div>
            <div className="font-display text-2xl font-bold mt-1 leading-tight">
              Snap a food bill
            </div>
            <div className="text-xs text-white/60 mt-1.5">
              {food.sub.join(' · ')}
            </div>
          </div>
          <ArrowRight className="w-5 h-5 text-lime mt-2 transition-transform group-hover:translate-x-1" />
        </div>
      </motion.button>

      {/* ------- Other categories grid ------- */}
      <motion.div
        initial="hidden" animate="show"
        variants={{ show: { transition: { staggerChildren: 0.03, delayChildren: 0.15 } } }}
        className="grid grid-cols-2 gap-3"
      >
        {otherCats.map(({ key, label, icon: Icon, sub }) => (
          <motion.button
            key={key}
            variants={{
              hidden: { opacity: 0, y: 12 },
              show: { opacity: 1, y: 0 },
            }}
            whileHover={{ y: -2 }}
            onClick={() => nav(`/app/category/${key}`)}
            data-testid={`category-${key}-card`}
            className="press-down group relative flat-card p-4 text-left hover:border-navy hover:shadow-[0_0_0_3px_rgba(212,255,0,0.20)] transition-all overflow-hidden"
          >
            {/* hover lime glow corner */}
            <div className="absolute top-0 right-0 w-16 h-16 bg-lime/0 group-hover:bg-lime/20 rounded-bl-full transition-colors" />

            <div className="relative">
              <div className="w-11 h-11 rounded-2xl bg-[#0A1128] text-lime grid place-items-center group-hover:bg-lime group-hover:text-navy transition-colors">
                <Icon className="w-5 h-5" strokeWidth={1.8} />
              </div>
              <div className="font-display font-bold text-base text-navy mt-3">{label}</div>
              <div className="text-[10px] text-slate-400 mt-0.5 font-medium">
                {sub.length} options
              </div>

              <ChevronRight className="absolute right-0 bottom-0 w-4 h-4 text-slate-300 group-hover:text-navy transition" />
            </div>
          </motion.button>
        ))}
      </motion.div>

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
