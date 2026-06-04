import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger, SheetDescription,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Download, Share2, CheckCircle2, FileText, Loader2, Wallet, Sparkles, MessageCircle, Mail } from 'lucide-react';
import { toast } from 'sonner';
import api, { API } from '@/lib/api';
import { useAuth } from '@/lib/auth';

export default function BillGen() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user, refreshUser } = useAuth();
  const [expense, setExpense] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [open, setOpen] = useState(false);

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

  const generate = async () => {
    setGenerating(true);
    try {
      const { data } = await api.post(`/bills/${id}/generate`);
      await refreshUser();
      await load();
      toast.success(`Bill ${data.bill_id} generated`);
      setOpen(false);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Generation failed');
    } finally { setGenerating(false); }
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

  return (
    <div className="pb-10">
      <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Step 7</div>
      <h1 className="font-display text-2xl font-bold text-navy mt-1">Payment captured</h1>
      <p className="text-sm text-slate-500 mt-1">Generate an official PDF invoice for reimbursement.</p>

      <div className="flat-card p-5 mt-5">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="w-6 h-6 text-emerald-500" />
          <div>
            <div className="font-display font-bold text-navy">Paid</div>
            <div className="text-xs text-slate-500">Transaction recorded</div>
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

            <div className="mt-5 flat-card p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Wallet className="w-5 h-5 text-navy" />
                <div>
                  <div className="text-xs text-slate-500">Bill generation fee</div>
                  <div className="font-mono font-bold text-navy">₹ 5.00</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs text-slate-500">Wallet balance</div>
                <div className="font-mono font-bold text-navy">₹ {user?.wallet_balance?.toFixed(2)}</div>
              </div>
            </div>

            {(user?.wallet_balance || 0) < 5 ? (
              <Button
                onClick={() => { setOpen(false); nav('/app/wallet'); }}
                className="press-down w-full h-12 mt-5 bg-navy text-white hover:bg-[#152042] rounded-full font-semibold"
                data-testid="recharge-wallet-btn"
              >
                Recharge wallet
              </Button>
            ) : (
              <Button
                onClick={generate} disabled={generating}
                className="press-down w-full h-12 mt-5 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
                data-testid="confirm-generate-btn"
              >
                {generating ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" />Generating...</>)
                  : 'Pay ₹5 from Wallet & Generate'}
              </Button>
            )}
          </SheetContent>
        </Sheet>
      )}

      {expense.bill_generated && (
        <div className="mt-6 space-y-3">
          <div className="flat-card p-5 bg-brand border-brand text-white">
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
