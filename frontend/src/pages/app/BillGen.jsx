import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger, SheetDescription,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { CheckCircle2, FileText, Loader2, Wallet, Sparkles, CreditCard } from 'lucide-react';
import { toast } from 'sonner';
import api from '@/lib/api';
import BillActions from '@/components/BillActions';
import { openRazorpay } from '@/lib/razorpay';
import { useAuth } from '@/lib/auth';

export default function BillGen() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user, refreshUser } = useAuth();
  const [expense, setExpense] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [open, setOpen] = useState(false);
  const [rzpEnabled, setRzpEnabled] = useState(false);
  const [feeMethod, setFeeMethod] = useState('wallet'); // 'wallet' | 'razorpay'
  const [feePercent, setFeePercent] = useState(1);
  const [walletPin, setWalletPin] = useState('');

  useEffect(() => {
    api.get('/payments/config').then(({ data }) => setRzpEnabled(!!data?.enabled)).catch(() => {});
    api.get('/bills/fee-info').then(({ data }) => {
      if (data?.percent != null) setFeePercent(Number(data.percent));
    }).catch(() => {});
  }, []);

  const load = async () => {
    try {
      const { data } = await api.get(`/expenses/${id}`);
      setExpense(data);
    } catch {
      toast.error('Expense not found');
      nav('/app/dashboard');
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  // Pick a sensible default fee method when the sheet opens: wallet if funded,
  // otherwise the QR/Razorpay option (when online payment is enabled).
  useEffect(() => {
    if (!open || !expense) return;
    const f = expense.bill_fee != null
      ? Number(expense.bill_fee)
      : (feePercent > 0 ? Math.max(1, Number(((Number(expense.total) || 0) * feePercent / 100).toFixed(2))) : 0);
    const walletOk = (Number(user?.wallet_balance) || 0) >= f;
    setFeeMethod(walletOk ? 'wallet' : (rzpEnabled ? 'razorpay' : 'wallet'));
    setWalletPin('');
  }, [open, expense, user, rzpEnabled, feePercent]);

  const generate = async (feeProof = null) => {
    setGenerating(true);
    try {
      const { data } = await api.post(`/bills/${id}/generate`, feeProof || {});
      await refreshUser();
      await load();
      toast.success(`Bill ${data.bill_id} generated`);
      setOpen(false);
    } catch (err) {
      if (err?.response?.status === 402) {
        toast.error('Wallet balance is too low — choose Online Payment to pay the fee via Razorpay.');
        setFeeMethod('razorpay');
      } else {
        toast.error(err?.response?.data?.detail || 'Generation failed');
      }
    } finally { setGenerating(false); }
  };

  const payFromWallet = async () => {
    if ((Number(user?.wallet_balance) || 0) < fee) {
      toast.error('Wallet balance is too low — choose Online Payment instead.');
      setFeeMethod('razorpay');
      return;
    }
    const pin = walletPin.trim();
    if (!/^\d{4}$/.test(pin)) {
      toast.error('Enter your 4-digit Wallet PIN');
      return;
    }
    await generate({ wallet_pin: pin });
  };

  const payFeeViaRazorpay = async () => {
    if (!rzpEnabled) {
      toast.error('Online payment is not enabled yet. Add Razorpay keys in backend/.env or pay from wallet.');
      return;
    }
    setGenerating(true);
    try {
      const { data: order } = await api.post('/payments/razorpay/order', { amount: fee, purpose: 'bill_fee' });
      await openRazorpay(order, {
        user,
        name: 'BILL4PE',
        description: `Bill Generation Charges · ₹${fee.toFixed(2)}`,
        onSuccess: async (resp) => {
          // Fee captured by Razorpay → generate the bill with the payment proof.
          await generate({
            razorpay_order_id: resp.razorpay_order_id,
            razorpay_payment_id: resp.razorpay_payment_id,
            razorpay_signature: resp.razorpay_signature,
          });
        },
        onDismiss: () => {
          setGenerating(false);
          toast.info('Payment cancelled. Your bill is still pending.');
        },
      });
    } catch (err) {
      setGenerating(false);
      if (err?.message !== 'CHECKOUT_DISMISSED') {
        toast.error(err?.response?.data?.detail || err?.message || 'Fee payment failed');
      }
    }
  };

  const handlePayAndGenerate = async () => {
    if (feeMethod === 'razorpay') await payFeeViaRazorpay();
    else await payFromWallet();
  };

  if (!expense) return <div className="py-10 text-center text-slate-400">Loading...</div>;
  const pay = expense.payment || {};
  const snap = expense.bill_snapshot || {};
  const isManual = snap.model === 'manual_upi_double_scan';
  // Authoritative fee from the server; fall back to legacy 1% only when absent.
  const fee = expense.bill_fee != null
    ? Number(expense.bill_fee)
    : (feePercent > 0 ? Math.max(1, Number(((Number(expense.total) || 0) * feePercent / 100).toFixed(2))) : 0);
  const walletOk = (Number(user?.wallet_balance) || 0) >= fee;
  const statusLabel = snap.merchant_payment_status_label || 'Paid';

  return (
    <div className="pb-10">
      <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">{expense.bill_generated ? 'Bill ready' : 'Step 7'}</div>
      <h1 className="font-display text-2xl font-bold text-navy mt-1">{expense.bill_generated ? 'Your bill is ready' : (isManual ? 'Payment confirmed by user' : 'Payment captured')}</h1>
      <p className="text-sm text-slate-500 mt-1">{expense.bill_generated ? 'Download or share your Bill4Pe digital receipt below.' : 'Generate your Bill4Pe digital expense receipt.'}</p>

      <div className="flat-card p-5 mt-5">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="w-6 h-6 text-emerald-500" />
          <div>
            <div className="font-display font-bold text-navy">{statusLabel}</div>
            <div className="text-xs text-slate-500">{isManual ? 'You paid the merchant directly via UPI' : 'Transaction recorded'}</div>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Merchant</div>
            <div className="font-semibold text-navy mt-1">{pay.merchant_name || '—'}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">UPI</div>
            <div className="font-mono text-xs text-navy mt-1 break-all">{pay.merchant_upi || '—'}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Txn ID</div>
            <div className="font-mono text-xs text-navy mt-1 break-all">{pay.transaction_id || '—'}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Amount</div>
            <div className="font-mono font-bold text-navy mt-1">₹ {Number(expense.total).toFixed(2)}</div>
          </div>
        </div>
      </div>

      <div className="flat-card p-5 mt-3">
        <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-semibold">Items</div>
        <div className="mt-3 divide-y divide-soft">
          {expense.items.map((it, i) => (
            <div key={i} className="flex items-center justify-between py-2 text-sm">
              <div>
                <div className="font-semibold text-navy">{it.name}</div>
                <div className="text-[10px] text-slate-400 font-mono">QTY {it.quantity} × ₹{it.unit_price}</div>
              </div>
              <div className="font-mono text-navy">₹ {(it.quantity * it.unit_price).toFixed(2)}</div>
            </div>
          ))}
        </div>
      </div>

      {!expense.bill_generated && (
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button
              className="press-down w-full h-12 mt-6 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
              data-testid="open-generate-sheet-btn"
            >
              <FileText className="w-4 h-4 mr-2" />Generate Official Bill
            </Button>
          </SheetTrigger>
          <SheetContent side="bottom" className="rounded-t-3xl border-0 px-5 pb-8 pt-7">
            <SheetHeader className="text-left">
              <div className="inline-flex items-center gap-1 self-start text-[10px] uppercase tracking-wider bg-lime text-navy px-2 py-0.5 rounded-full font-bold">
                <Sparkles className="w-3 h-3" /> Premium
              </div>
              <SheetTitle className="font-display text-2xl text-navy mt-2">Generate official bill</SheetTitle>
              <SheetDescription className="text-slate-500">
                A professional PDF invoice ready for corporate reimbursement.
              </SheetDescription>
            </SheetHeader>

            {fee > 0 ? (
              <>
                <div className="mt-5 flat-card p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Wallet className="w-5 h-5 text-navy" />
                    <div>
                      <div className="text-xs text-slate-500">Bill Generation Charges (@ {feePercent % 1 === 0 ? feePercent : Number(feePercent).toFixed(2)}% of billed amount)</div>
                      <div className="font-mono font-bold text-navy" data-testid="bill-fee-amount">₹ {fee.toFixed(2)}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-slate-500">Wallet balance</div>
                    <div className="font-mono font-bold text-navy">₹ {Number(user?.wallet_balance || 0).toFixed(2)}</div>
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-semibold mb-2">
                    Choose how to pay the fee
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <button
                      type="button"
                      onClick={() => setFeeMethod('wallet')}
                      data-testid="fee-method-wallet"
                      className={`text-left rounded-2xl border-2 p-4 transition-colors ${feeMethod === 'wallet' ? 'border-brand bg-brand/5' : 'border-soft'}`}
                    >
                      <div className="flex items-center justify-between">
                        <Wallet className={`w-5 h-5 ${feeMethod === 'wallet' ? 'text-brand' : 'text-slate-400'}`} />
                        {feeMethod === 'wallet' && <CheckCircle2 className="w-4 h-4 text-brand" />}
                      </div>
                      <div className="font-semibold text-navy mt-2">Wallet</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        {walletOk ? 'Pay from balance' : 'Low balance'}
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setFeeMethod('razorpay')}
                      data-testid="fee-method-razorpay"
                      className={`text-left rounded-2xl border-2 p-4 transition-colors ${feeMethod === 'razorpay' ? 'border-brand bg-brand/5' : 'border-soft'}`}
                    >
                      <div className="flex items-center justify-between">
                        <CreditCard className={`w-5 h-5 ${feeMethod === 'razorpay' ? 'text-brand' : 'text-slate-400'}`} />
                        {feeMethod === 'razorpay' && <CheckCircle2 className="w-4 h-4 text-brand" />}
                      </div>
                      <div className="font-semibold text-navy mt-2">Online Payment</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        {rzpEnabled ? 'UPI / PhonePe / Paytm (where available) via Razorpay' : 'Razorpay setup pending'}
                      </div>
                    </button>
                  </div>
                </div>

                {feeMethod === 'wallet' && (
                  <div className="mt-4">
                    <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Wallet PIN</label>
                    <Input
                      type="password" inputMode="numeric" autoComplete="off" maxLength={4}
                      value={walletPin}
                      onChange={(e) => setWalletPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
                      placeholder="Enter 4-digit Wallet PIN"
                      className="mt-1 h-12 rounded-xl font-mono tracking-[0.35em]"
                      data-testid="bill-wallet-pin-input"
                    />
                    <p className="text-[11px] text-slate-400 mt-1">The same 4-digit PIN you created when setting up your wallet.</p>
                  </div>
                )}

                <Button
                  onClick={handlePayAndGenerate}
                  disabled={generating || (feeMethod === 'wallet' && (!walletOk || walletPin.length !== 4)) || (feeMethod === 'razorpay' && !rzpEnabled)}
                  className="press-down w-full h-12 mt-5 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold disabled:opacity-60"
                  data-testid="confirm-generate-btn"
                >
                  {generating ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" />Processing...</>)
                    : feeMethod === 'razorpay'
                      ? (<><CreditCard className="w-4 h-4 mr-2" />Pay ₹{fee.toFixed(2)} Online &amp; Generate</>)
                      : (<><Wallet className="w-4 h-4 mr-2" />Pay ₹{fee.toFixed(2)} from Wallet &amp; Generate</>)}
                </Button>
                <p className="text-[11px] text-slate-400 text-center mt-2 leading-snug">
                  {feeMethod === 'razorpay'
                    ? 'Pay securely through Razorpay using available online methods. Your bill is generated only after payment succeeds.'
                    : (walletOk
                        ? 'Enter your Wallet PIN to approve the deduction. A wrong PIN will not debit the wallet or generate the bill.'
                        : 'Wallet is short — switch to Online Payment or recharge your wallet.')}
                </p>
              </>
            ) : (
              <>
                <div className="mt-5 flat-card p-4 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-700 grid place-items-center shrink-0">
                    <CheckCircle2 className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-navy" data-testid="bill-fee-amount">No Bill Generation Charges</div>
                    <div className="text-[11px] text-slate-500">
                      {user?.user_type === 'corporate'
                        ? 'Included in your company subscription — generate unlimited bills.'
                        : 'No fee applies to this bill.'}
                    </div>
                  </div>
                </div>

                <Button
                  onClick={() => generate()}
                  disabled={generating}
                  className="press-down w-full h-12 mt-5 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold disabled:opacity-60"
                  data-testid="confirm-generate-btn"
                >
                  {generating ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" />Generating...</>)
                    : (<><FileText className="w-4 h-4 mr-2" />Generate bill</>)}
                </Button>
                <p className="text-[11px] text-slate-400 text-center mt-2 leading-snug">
                  Your official PDF bill will be generated instantly.
                </p>
              </>
            )}
          </SheetContent>
        </Sheet>
      )}

      {expense.bill_generated && (
        <div className="mt-6 space-y-3">
          <div className="flat-card p-5 border-brand text-white" style={{ backgroundColor: 'var(--brand)' }}>
            <div className="text-[10px] uppercase tracking-wider text-white/70 font-bold">Bill ID</div>
            <div className="font-mono font-bold text-white text-lg" data-testid="bill-id">{expense.bill_id}</div>
          </div>
          <BillActions key={expense.id || id} expense={{ ...expense, id: expense.id || id }} />
          <button
            onClick={() => nav('/app/dashboard')}
            className="w-full h-12 text-slate-500 underline text-sm"
          >
            Back to dashboard
          </button>
        </div>
      )}
    </div>
  );
}
