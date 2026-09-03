import React, { useEffect, useState } from 'react';
import { Wallet as WalletIcon, ArrowDownLeft, ArrowUpRight, Plus, CreditCard } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger, SheetDescription,
} from '@/components/ui/sheet';
import { toast } from 'sonner';
import api from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { openRazorpay } from '@/lib/razorpay';

const QUICK = [100, 200, 500, 1000];

export default function Wallet() {
  const { user, refreshUser } = useAuth();
  const [data, setData] = useState({ balance: 0, transactions: [] });
  const [payments, setPayments] = useState([]);
  const [open, setOpen] = useState(false);
  const [amt, setAmt] = useState(200);
  const [loading, setLoading] = useState(false);

  const isEmployee = user?.role === 'employee';

  const load = async () => {
    const [{ data: w }, { data: p }] = await Promise.all([
      api.get('/wallet'),
      api.get('/payments/history'),
    ]);
    setData(w);
    setPayments(p.payments || []);
  };
  useEffect(() => { load(); }, []);

  const recharge = async () => {
    const a = Number(amt);
    if (!a || a <= 0) { toast.error('Enter a valid amount'); return; }
    setLoading(true);
    try {
      const { data: order } = await api.post('/payments/razorpay/order', { amount: a, purpose: 'wallet_recharge' });
      await openRazorpay(order, {
        user,
        name: 'BILL4PE Wallet',
        description: `Add ₹${a} to wallet`,
        onSuccess: async (resp) => {
          await api.post('/payments/razorpay/verify', {
            razorpay_order_id: resp.razorpay_order_id,
            razorpay_payment_id: resp.razorpay_payment_id,
            razorpay_signature: resp.razorpay_signature,
            purpose: 'wallet_recharge',
          });
          await load();
          await refreshUser();
          toast.success(`₹${a} added to wallet`);
          setOpen(false);
        },
      });
    } catch (err) {
      if (err?.message !== 'CHECKOUT_DISMISSED') {
        toast.error(err?.response?.data?.detail || err?.message || 'Recharge failed');
      }
    } finally { setLoading(false); }
  };

  return (
    <div className="space-y-5">
      <h1 className="font-display text-2xl font-bold text-navy">Wallet</h1>

      <div className="bg-navy text-white rounded-3xl p-6 relative overflow-hidden">
        <div className="absolute inset-0 opacity-20"
             style={{ background: 'radial-gradient(circle at 90% 10%, rgba(31,111,235,0.5), transparent 50%)' }} />
        <div className="relative">
          <div className="flex items-center gap-2 text-brand text-[10px] uppercase tracking-[0.3em] font-bold">
            <WalletIcon className="w-3.5 h-3.5" /> Available balance
          </div>
          <div className="font-mono text-4xl font-bold mt-3" data-testid="wallet-balance">
            ₹ {data.balance.toFixed(2)}
          </div>
          <div className="text-[11px] text-white/60 mt-1.5 leading-snug">
            {isEmployee
              ? 'Your bills are billed to the company wallet — your admin handles top-ups. Reach out to them if needed.'
              : 'Prepaid pool · auto-adjusted against the 1% convenience fee (min ₹1) per generated bill. New users get ₹50 free credit.'}
          </div>
          {!isEmployee && (
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <button
                className="press-down mt-6 inline-flex items-center gap-2 bg-brand text-white px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-[#1858CC]"
                data-testid="recharge-btn"
              >
                <Plus className="w-4 h-4" /> Recharge
              </button>
            </SheetTrigger>
            <SheetContent side="bottom" className="rounded-t-3xl border-0 px-5 pb-8 pt-7">
              <SheetHeader className="text-left">
                <SheetTitle className="font-display text-2xl text-navy">Recharge wallet</SheetTitle>
                <SheetDescription className="text-slate-500">
                  Secure payment via Razorpay. Credited instantly on success.
                </SheetDescription>
              </SheetHeader>
              <div className="mt-5 flex gap-2">
                {QUICK.map((q) => (
                  <button
                    key={q}
                    onClick={() => setAmt(q)}
                    className={`press-down flex-1 py-3 rounded-xl font-semibold text-sm ${amt === q ? 'bg-navy text-white' : 'bg-[#0A1128]/5 text-navy'}`}
                    data-testid={`quick-amt-${q}`}
                  >₹{q}</button>
                ))}
              </div>
              <div className="mt-4">
                <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Or enter amount</label>
                <Input
                  type="number" min="1" max="10000" value={amt}
                  onChange={(e) => setAmt(e.target.value)}
                  className="mt-1 h-12 rounded-xl border-soft font-mono"
                  data-testid="recharge-amount-input"
                />
              </div>
              <Button
                onClick={recharge} disabled={loading}
                className="press-down w-full h-12 mt-5 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
                data-testid="confirm-recharge-btn"
              >
                {loading ? 'Processing...' : `Add ₹${amt}`}
              </Button>
            </SheetContent>
          </Sheet>
          )}
        </div>
      </div>

      <div>
        <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Transactions</div>
        <div className="mt-3 space-y-2">
          {data.transactions.length === 0 && (
            <div className="flat-card p-8 text-center text-slate-400 text-sm">No wallet activity yet.</div>
          )}
          {data.transactions.map((t) => (
            <div key={t.id} className="flat-card p-4 flex items-center gap-3" data-testid={`txn-${t.id}`}>
              <div className={`w-10 h-10 rounded-xl grid place-items-center ${t.type === 'credit' ? 'bg-emerald-500/10 text-emerald-600' : 'bg-red-500/10 text-red-600'}`}>
                {t.type === 'credit' ? <ArrowDownLeft className="w-5 h-5" /> : <ArrowUpRight className="w-5 h-5" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-navy text-sm truncate">{t.reason}</div>
                <div className="text-[10px] text-slate-400 font-mono mt-0.5">{t.created_at?.slice(0, 19).replace('T', ' ')}</div>
              </div>
              <div className={`font-mono font-bold ${t.type === 'credit' ? 'text-emerald-600' : 'text-red-600'}`}>
                {t.type === 'credit' ? '+' : '−'} ₹{Number(t.amount).toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Razorpay Payments</div>
        <div className="mt-3 space-y-2" data-testid="razorpay-history">
          {payments.length === 0 && (
            <div className="flat-card p-8 text-center text-slate-400 text-sm">No Razorpay payments yet.</div>
          )}
          {payments.map((p) => (
            <div key={p.order_id} className="flat-card p-4 flex items-center gap-3" data-testid={`rzp-${p.order_id}`}>
              <div className={`w-10 h-10 rounded-xl grid place-items-center ${p.status === 'paid' ? 'bg-emerald-500/10 text-emerald-600' : 'bg-amber-500/10 text-amber-600'}`}>
                <CreditCard className="w-5 h-5" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-navy text-sm">
                  {p.purpose === 'wallet_recharge' ? 'Wallet recharge' : 'Bill payment'}
                </div>
                <div className="text-[10px] text-slate-400 font-mono mt-0.5 truncate">
                  {p.payment_id || p.order_id} · {p.created_at?.slice(0, 19).replace('T', ' ')}
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono font-bold text-navy">₹{Number(p.amount).toFixed(2)}</div>
                <span className={`inline-block mt-0.5 text-[9px] uppercase tracking-wide font-bold px-1.5 py-0.5 rounded ${p.status === 'paid' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                  {p.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
