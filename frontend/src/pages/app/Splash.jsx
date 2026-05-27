import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Wallet as WalletIcon, ArrowRight } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { CATEGORIES } from '@/lib/categories';

export default function Splash() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [showCats, setShowCats] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setShowCats(true), 900);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
        className="bg-navy text-white rounded-2xl p-5 relative overflow-hidden"
      >
        <div className="absolute inset-0 opacity-20"
             style={{ background: 'radial-gradient(circle at 80% 20%, rgba(212,255,0,0.4), transparent 50%)' }} />
        <div className="relative">
          <div className="text-[10px] tracking-[0.3em] text-lime/80">PAY YOUR BILL</div>
          <div className="font-display text-2xl font-bold mt-2">Hi, {user?.name?.split(' ')[0] || 'there'}.</div>
          <p className="text-white/60 text-sm mt-1">AI Powered Expense & Invoice Platform.</p>

          <button
            onClick={() => nav('/app/wallet')}
            data-testid="splash-wallet-btn"
            className="press-down mt-5 flex items-center justify-between w-full bg-white/10 hover:bg-white/15 border border-white/10 rounded-xl px-4 py-3"
          >
            <span className="flex items-center gap-2">
              <WalletIcon className="w-4 h-4 text-lime" />
              <span className="text-xs uppercase tracking-wider text-white/60">Wallet</span>
            </span>
            <span className="font-mono font-bold text-lg" data-testid="splash-wallet-balance">
              ₹ {user?.wallet_balance?.toFixed(2) ?? '0.00'}
            </span>
          </button>
        </div>
      </motion.div>

      <div>
        <div className="flex items-end justify-between">
          <div>
            <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Pick a category</div>
            <h2 className="font-display text-2xl font-bold text-navy mt-1.5">What did you spend on?</h2>
          </div>
        </div>

        <motion.div
          initial="hidden" animate={showCats ? 'show' : 'hidden'}
          variants={{ show: { transition: { staggerChildren: 0.04 } } }}
          className="grid grid-cols-2 gap-3 mt-5"
        >
          {CATEGORIES.map(({ key, label, icon: Icon }) => (
            <motion.button
              key={key}
              variants={{ hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}
              onClick={() => nav(`/app/category/${key}`)}
              data-testid={`category-${key}-card`}
              className="press-down group flat-card p-4 text-left hover:border-navy transition-colors relative overflow-hidden"
            >
              <div className="w-10 h-10 rounded-xl bg-[#0A1128]/5 grid place-items-center group-hover:bg-lime transition-colors">
                <Icon className="w-5 h-5 text-navy" strokeWidth={1.8} />
              </div>
              <div className="font-display font-semibold text-base text-navy mt-3">{label}</div>
              <ArrowRight className="w-4 h-4 text-slate-300 absolute right-4 top-4 group-hover:text-navy transition" />
            </motion.button>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
