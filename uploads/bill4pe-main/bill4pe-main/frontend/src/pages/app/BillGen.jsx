import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger, SheetDescription,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Download, Share2, CheckCircle2, FileText, Loader2, Wallet, Sparkles, MessageCircle, Mail, QrCode } from 'lucide-react';
import { toast } from 'sonner';
import api, { API } from '@/lib/api';
import { openRazorpay } from '@/lib/razorpay';
import { useAuth } from '@/lib/auth';

export default function BillGen() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user, refreshUser } = useAuth();
  const [expense, setExpense] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [open, setOpen] = useState(false);
  const [emailOpen, setEmailOpen] = useState(false);
  const [clientEmail, setClientEmail] = useState('');
  const [sending, setSending] = useState(false);
  const [rzpEnabled, setRzpEnabled] = useState(false);
  const [feeMethod, setFeeMethod] = useState('wallet'); // 'wallet' | 'qr'
  const [feePercent, setFeePercent] = useState(1);

  useEffect(() => {
    api.get('/payments/config').then(({ data }) => setRzpEnabled(!!data?.enabled)).catch(() => {});
    api.get('/bills/fee-info').then(({ data }) => {
      if (data?.percent != null) setFeePercent(Number(data.percent));
    }).catch(() => {});
  }, []);

  const sendInvoiceEmail = async () => {
    if (!clientEmail.trim()) { toast.error('Enter client email'); return; }
    setSending(true);
    try {
      const verify_url = `${window.location.origin}/verify/${expense.bill_id}`;
      await api.post(`/bills/${id}/email`, { recipient_email: clientEmail.trim(), verify_url });
      toast.success(`Invoice emailed to ${clientEmail.trim()}`);
      setEmailOpen(false);
      setClientEmail('');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not send email');
    } finally { setSending(false); }
  };

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
    setFeeMethod(walletOk ? 'wallet' : (rzpEnabled ? 'qr' : 'wallet'));
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
        toast.error('Wallet balance is too low — choose "QR / UPI" to pay the fee online.');
        setFeeMethod('qr');
      } else {
        toast.error(err?.response?.data?.detail || 'Generation failed');
      }
    } finally { setGenerating(false); }
  };

  const payFromWallet = async () => {
    if ((Number(user?.wallet_balance) || 0) < fee) {
      toast.error('Wallet balance is too low — choose "QR / UPI" instead.');
      setFeeMethod('qr');
      return;
    }
    await generate();
  };

  const payFeeViaRazorpay = async () => {
    if (!rzpEnabled) {
      toast.error('Online (QR / UPI) payment is not enabled yet. Please pay from wallet.');
      return;
    }
    setGenerating(true);
    try {
      const { data: order } = await api.post('/payments/razorpay/order', { amount: fee, purpose: 'bill_fee' });
      await openRazorpay(order, {
        user,
        name: 'BILL4PE',
        description: `Bill convenience fee · ₹${fee.toFixed(2)}`,
        onSuccess: async (resp) => {
          // Fee captured by Razorpay → generate the bill with the payment proof.
          await generate({
            razorpay_order_id: resp.razorpay_order_id,
            razorpay_payment_id: resp.razorpay_payment_id,
            razorpay_signature: resp.razorpay_signature,
          });
        },
        onDismiss: () => setGenerating(false),
      });
    } catch (err) {
      setGenerating(false);
      if (err?.message !== 'CHECKOUT_DISMISSED') {
        toast.error(err?.response?.data?.detail || err?.message || 'Fee payment failed');
      }
    }
  };

  const handlePayAndGenerate = async () => {
    if (feeMethod === 'qr') await payFeeViaRazorpay();
    else await payFromWallet();
  };

  const pdfUrl = () => {
    const token = localStorage.getItem('bill4pe_token');
    return `${API}/bills/${id}/pdf?token=${encodeURIComponent(token || '')}`;
  };

  const share = async () => {
    const url = pdfUrl();
    if (navigator.share) {
      try { await navigator.share({ title: `BILL4PE Invoice ${expense?.bill_id || ''}`, url }); }
      catch { /* user cancelled */ }
    } else {
      navigator.clipboard?.writeText(url);
      toast.success('Invoice link copied');
    }
  };

  const shareWhatsApp = () => {
    const url = pdfUrl();
    const msg = `BILL4PE Invoice ${expense?.bill_id || ''}\nAmount: ₹${Number(expense?.total || 0).toFixed(2)}\nMerchant: ${pay.merchant_name || '—'}\n\nView / Download: ${url}\n\n— Sent via BILL4PE · An Intelligent Billing`;
    window.open(`https://wa.me/?text=${encodeURIComponent(msg)}`, '_blank', 'noopener,noreferrer');
  };

  const shareEmail = () => {
    const url = pdfUrl();
    const subject = `Reimbursement Invoice ${expense?.bill_id || ''} — ₹${Number(expense?.total || 0).toFixed(2)}`;
    const body = `Hi,\n\nPlease find my expense invoice attached.\n\nBill ID: ${expense?.bill_id || ''}\nMerchant: ${pay.merchant_name || '—'}\nAmount: ₹${Number(expense?.total || 0).toFixed(2)}\nTransaction ID: ${pay.transaction_id || '—'}\n\nDownload / verify: ${url}\n\nThanks,\n${user?.name || ''}\n\n— Sent via BILL4PE · bill4pe.com`;
    window.location.href = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
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
                      <div className="text-xs text-slate-500">Bill convenience fee ({feePercent % 1 === 0 ? feePercent : Number(feePercent).toFixed(2)}% of bill)</div>
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
                      onClick={() => setFeeMethod('qr')}
                      data-testid="fee-method-qr"
                      className={`text-left rounded-2xl border-2 p-4 transition-colors ${feeMethod === 'qr' ? 'border-brand bg-brand/5' : 'border-soft'}`}
                    >
                      <div className="flex items-center justify-between">
                        <QrCode className={`w-5 h-5 ${feeMethod === 'qr' ? 'text-brand' : 'text-slate-400'}`} />
                        {feeMethod === 'qr' && <CheckCircle2 className="w-4 h-4 text-brand" />}
                      </div>
                      <div className="font-semibold text-navy mt-2">QR / UPI</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        {rzpEnabled ? 'Pay via Razorpay' : 'Setup pending'}
                      </div>
                    </button>
                  </div>
                </div>

                <Button
                  onClick={handlePayAndGenerate}
                  disabled={generating || (feeMethod === 'wallet' && !walletOk)}
                  className="press-down w-full h-12 mt-5 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold disabled:opacity-60"
                  data-testid="confirm-generate-btn"
                >
                  {generating ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" />Processing...</>)
                    : feeMethod === 'qr'
                      ? (<><QrCode className="w-4 h-4 mr-2" />Pay ₹{fee.toFixed(2)} via QR &amp; Generate</>)
                      : (<><Wallet className="w-4 h-4 mr-2" />Pay ₹{fee.toFixed(2)} from Wallet &amp; Generate</>)}
                </Button>
                <p className="text-[11px] text-slate-400 text-center mt-2 leading-snug">
                  {feeMethod === 'qr'
                    ? 'Scan the QR / pay via UPI in the Razorpay window — your bill is generated right after payment succeeds.'
                    : (walletOk
                        ? 'Fee is deducted from your wallet balance.'
                        : 'Wallet is short — switch to QR / UPI to pay online.')}
                </p>
              </>
            ) : (
              <>
                <div className="mt-5 flat-card p-4 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-700 grid place-items-center shrink-0">
                    <CheckCircle2 className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-navy" data-testid="bill-fee-amount">No convenience fee</div>
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
          <a
            href={pdfUrl()} target="_blank" rel="noopener noreferrer"
            className="press-down w-full h-12 bg-navy text-white hover:bg-[#152042] rounded-full font-semibold flex items-center justify-center gap-2"
            data-testid="download-pdf-btn"
          >
            <Download className="w-4 h-4" /> View / Download PDF
          </a>
          <button
            onClick={share}
            className="press-down w-full h-12 border-2 border-navy text-navy rounded-full font-semibold flex items-center justify-center gap-2"
            data-testid="share-bill-btn"
          >
            <Share2 className="w-4 h-4" /> Share
          </button>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={shareWhatsApp}
              className="press-down h-12 rounded-full font-semibold flex items-center justify-center gap-2 bg-[#25D366] text-white hover:brightness-95"
              data-testid="share-whatsapp-btn"
            >
              <MessageCircle className="w-4 h-4" /> WhatsApp
            </button>
            <button
              onClick={shareEmail}
              className="press-down h-12 rounded-full font-semibold flex items-center justify-center gap-2 bg-white border-2 border-navy text-navy"
              data-testid="share-email-btn"
            >
              <Mail className="w-4 h-4" /> Email
            </button>
          </div>
          <Sheet open={emailOpen} onOpenChange={setEmailOpen}>
            <SheetTrigger asChild>
              <button
                data-testid="email-invoice-btn"
                className="press-down w-full h-12 rounded-full font-semibold flex items-center justify-center gap-2 bg-brand text-white hover:bg-[#1858CC]"
              >
                <Mail className="w-4 h-4" /> Email invoice to client
              </button>
            </SheetTrigger>
            <SheetContent side="bottom" className="rounded-t-3xl border-0 px-5 pb-8 pt-7">
              <SheetHeader className="text-left">
                <SheetTitle className="font-display text-2xl text-navy">Email invoice</SheetTitle>
                <SheetDescription className="text-slate-500">
                  Send invoice {expense.bill_id} to your client's email — includes a secure verify link.
                </SheetDescription>
              </SheetHeader>
              <div className="mt-5">
                <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Client email</label>
                <Input
                  type="email" value={clientEmail}
                  onChange={(e) => setClientEmail(e.target.value)}
                  placeholder="client@company.com"
                  className="mt-1 h-12 rounded-xl border-soft"
                  data-testid="client-email-input"
                />
              </div>
              <Button
                onClick={sendInvoiceEmail} disabled={sending}
                className="press-down w-full h-12 mt-5 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
                data-testid="send-invoice-email-btn"
              >
                {sending ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" />Sending...</>) : 'Send invoice'}
              </Button>
            </SheetContent>
          </Sheet>
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
