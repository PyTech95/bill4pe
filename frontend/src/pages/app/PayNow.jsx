import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Loader2, CheckCircle2, XCircle, ArrowLeft, ReceiptText } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import api from '@/lib/api';
import { openRazorpay } from '@/lib/razorpay';
import { useAuth } from '@/lib/auth';

const TXN_KEY = 'bill4pe_manual_txn';
const money = (n) => `₹${Number(n || 0).toFixed(2)}`;

// Only these money-sensitive states are worth auto-resuming (the receipt upload
// step included — we must not lose an in-progress verification). Cancelled/
// discarded/superseded attempts return 404 and are never resumed.
const RESUMABLE = ['awaiting_merchant_payment', 'merchant_payment_claimed', 'proof_submitted', 'fee_due', 'fee_pending'];

function CheckRow({ label, value, ok, mono }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 text-sm">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className={`flex items-center gap-1.5 font-medium text-right break-all ${mono ? 'font-mono' : ''}`}>
        {ok === true && <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />}
        {ok === false && <XCircle className="h-4 w-4 text-red-600 shrink-0" />}
        <span className={ok === false ? 'text-red-700' : ''}>{value}</span>
      </span>
    </div>
  );
}

// Read-only verification result — every value comes from server-side OCR of the
// uploaded receipt. Nothing here is editable.
function VerificationCard({ v, billAmount }) {
  if (!v) return null;
  const statusLabel = { success: 'Successful', failed: 'Failed', pending: 'Pending', unknown: 'Not readable' }[v.payment_status] || v.payment_status || 'Not readable';
  const final = v.verification_status;
  return (
    <div className="rounded-xl border overflow-hidden" data-testid="verification-card">
      <div className="px-4 py-3 bg-muted/40 border-b">
        <h3 className="font-semibold text-sm">Payment Receipt Verification</h3>
        <p className="text-[11px] text-muted-foreground mt-0.5">Auto-extracted from your receipt · not editable</p>
      </div>
      <div className="px-4 py-2 divide-y divide-border/60">
        <CheckRow label="Payment Status" value={statusLabel} ok={v.payment_status === 'success' ? true : (v.payment_status === 'unknown' ? null : false)} />
        <CheckRow label="Bill Amount" value={money(billAmount)} mono />
        <CheckRow label="Payment Amount" value={v.extracted_amount != null ? money(v.extracted_amount) : 'Not readable'} ok={v.extracted_amount != null ? true : null} mono />
        <CheckRow label="Amount Match" value={v.amount_matched ? 'Matched' : 'Mismatch'} ok={v.amount_matched} />
        <CheckRow label="Receiver" value={v.payee_name || '—'} />
        <CheckRow label="Receiver UPI" value={v.payee_upi || '—'} mono />
        {v.receiver_matched !== null && v.receiver_matched !== undefined && (
          <CheckRow label="Receiver Match" value={v.receiver_matched ? 'Matched' : 'Mismatch'} ok={v.receiver_matched} />
        )}
        <CheckRow label="UTR / UPI Ref" value={v.extracted_utr || 'Not readable'} ok={v.extracted_utr ? true : null} mono />
        <CheckRow label="Transaction ID" value={v.extracted_transaction_id || '—'} mono />
        <CheckRow label="Payment App" value={v.payment_provider || '—'} />
        <CheckRow label="Date" value={v.transaction_date || '—'} mono />
        <CheckRow label="Time" value={v.transaction_time || '—'} mono />
        <CheckRow label="Duplicate Check" value={v.duplicate_check === 'duplicate' ? 'Already used' : 'New Transaction'} ok={v.duplicate_check !== 'duplicate'} />
      </div>
      {(v.failure_reasons || []).length > 0 && final !== 'verified' && (
        <ul className="px-4 pb-3 space-y-1" data-testid="verification-failures">
          {v.failure_reasons.map((r, i) => (
            <li key={i} className="text-xs text-red-600 flex items-start gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />{r}
            </li>
          ))}
        </ul>
      )}
      <div
        data-testid="verification-final-status"
        className={`px-4 py-3 text-sm font-bold flex items-center gap-2 ${
          final === 'verified' ? 'bg-emerald-50 text-emerald-700'
            : final === 'rejected' ? 'bg-red-50 text-red-700'
            : 'bg-amber-50 text-amber-700'
        }`}
      >
        {final === 'verified'
          ? <><CheckCircle2 className="h-5 w-5" /> PAYMENT VERIFIED</>
          : final === 'rejected'
            ? <><XCircle className="h-5 w-5" /> PAYMENT NOT VERIFIED</>
            : <><AlertTriangle className="h-5 w-5" /> REVIEW REQUIRED</>}
      </div>
    </div>
  );
}

export default function PayNow() {
  const nav = useNavigate();
  const { user, refreshUser } = useAuth();
  const isCorporate = user?.user_type === 'corporate';
  const autoGenRef = useRef(false);
  const [genError, setGenError] = useState(false);
  const [draft, setDraft] = useState(null);
  const [txn, setTxn] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [needsFee, setNeedsFee] = useState(null);
  const [payeeAmount, setPayeeAmount] = useState('');
  const [discardOpen, setDiscardOpen] = useState(false);

  // Load draft + resume any pending transaction (app-close recovery).
  const refresh = useCallback(async (tid) => {
    try { const { data } = await api.get(`/manual-pay/${tid}`); setTxn(data); return data; }
    catch { localStorage.removeItem(TXN_KEY); setTxn(null); return null; }
  }, []);

  useEffect(() => {
    let d = null;
    try { d = JSON.parse(sessionStorage.getItem('bill4pe_draft') || 'null'); } catch { /* */ }
    setDraft(d);
    const tid = localStorage.getItem(TXN_KEY);
    (async () => {
      if (tid) {
        try {
          const { data } = await api.get(`/manual-pay/${tid}`);
          if (data && !data.bill_id && RESUMABLE.includes(data.state)) {
            const currentTotal = d?.items?.reduce((s, i) => s + (Number(i.quantity) || 1) * (Number(i.unit_price) || 0), 0) || 0;
            if (d && currentTotal > 0 && Math.abs((data.merchant_amount || 0) - currentTotal) > 0.005) {
              // Bill contents changed since this attempt opened — invalidate the
              // stale attempt server-side and start fresh with the new bill.
              api.post(`/manual-pay/${tid}/discard`).catch(() => {});
              localStorage.removeItem(TXN_KEY);
              setTxn(null);
            } else {
              setTxn(data); // resume the in-progress, money-sensitive payment
            }
          } else {
            if (data && data.state === 'second_qr_required') {
              api.post(`/manual-pay/${tid}/cancel`).catch(() => {});
              localStorage.removeItem(TXN_KEY);
              setTxn(null);
            }
            localStorage.removeItem(TXN_KEY);
            setTxn(null);
          }
        } catch { localStorage.removeItem(TXN_KEY); setTxn(null); }
      }
      setLoading(false);
    })();
  }, []);

  // Re-check authoritative state whenever the user returns to the tab.
  useEffect(() => {
    const onVis = () => { const tid = localStorage.getItem(TXN_KEY); if (tid && document.visibilityState === 'visible') refresh(tid); };
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, [refresh]);

  const draftAmount = draft?.items?.reduce((s, i) => s + (Number(i.quantity) || 1) * (Number(i.unit_price) || 0), 0) || 0;
  const verified = txn?.merchant_verification_status === 'verified' || txn?.merchant_verification_status === 'admin_reviewed';

  // Pay Now → create the payment attempt and go STRAIGHT to receipt upload.
  // No payee questions: the payee is captured from the receipt OCR.
  const startPayment = async () => {
    const amt = draft ? undefined : Number(payeeAmount);
    if (!draft && (!amt || amt <= 0)) { toast.error('Enter the payment amount'); return; }
    setBusy(true);
    try {
      const { data } = await api.post('/manual-pay/first-scan', {
        merchant_amount: amt,
        expense_draft: draft || undefined,
      });
      localStorage.setItem(TXN_KEY, data.transaction_id);
      setTxn(data);
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not start payment'); }
    finally { setBusy(false); }
  };

  // Receipt upload → server reads the screenshot (amount, UTR, payee, status),
  // cross-checks it against the bill and returns the verification result.
  const uploadProof = async (file) => {
    if (!file) return;
    setVerifying(true);
    try {
      const fd = new FormData();
      fd.append('screenshot', file);
      const { data } = await api.post(`/manual-pay/${txn.transaction_id}/proof`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setTxn(data);
      if (data?.verification?.verification_status === 'verified') toast.success('Payment verified ✓');
      else toast.error('Payment not verified — see the details below');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not verify the receipt');
    } finally {
      setVerifying(false);
    }
  };

  const generate = async () => {
    setBusy(true); setNeedsFee(null); setGenError(false);
    try {
      const { data } = await api.post(`/manual-pay/${txn.transaction_id}/generate`);
      if (data.needs_fee) { setNeedsFee(data); setTxn(data); toast.message('Service fee due'); return; }
      setTxn(data); await refreshUser();
      toast.success('Receipt generated ✓');
    } catch (e) { setGenError(true); toast.error(e.response?.data?.detail || 'Could not generate receipt'); }
    finally { setBusy(false); }
  };

  // Corporate = monthly subscription -> generate the bill AUTOMATICALLY once the
  // payment is VERIFIED, with no manual "generate" prompt.
  useEffect(() => {
    if (!isCorporate) return;
    const state = txn?.state;
    const ready = verified && (state === 'proof_submitted' || state === 'fee_due' || state === 'fee_pending');
    if (ready && !txn?.bill_id && !busy && !autoGenRef.current) {
      autoGenRef.current = true;
      generate();
    }
  }, [txn, isCorporate, busy, verified]); // eslint-disable-line react-hooks/exhaustive-deps

  const payFeeRazorpay = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/manual-pay/${txn.transaction_id}/fee-order`);
      await openRazorpay(
        { order_id: data.razorpay_order_id, amount: data.amount_paise, currency: 'INR', key_id: data.razorpay_key_id },
        {
          name: 'BILL4PE', description: 'Bill4Pe service fee',
          onSuccess: async (resp) => {
            try {
              const { data: v } = await api.post(`/manual-pay/${txn.transaction_id}/fee-verify`, {
                razorpay_order_id: resp.razorpay_order_id, razorpay_payment_id: resp.razorpay_payment_id, razorpay_signature: resp.razorpay_signature,
              });
              setTxn(v); setNeedsFee(null); toast.success('Fee paid — receipt generated ✓');
            } catch (e) { toast.error(e.response?.data?.detail || 'Fee verification failed'); }
          },
        },
      );
    } catch (e) { toast.error(e.response?.data?.detail || 'Top up your wallet instead (Razorpay not configured)'); }
    finally { setBusy(false); }
  };

  // Start a NEW payment attempt for the SAME bill: the old attempt is cancelled
  // server-side and the fresh attempt has an empty receipt/OCR/verification state.
  const startNew = async () => {
    const tid = txn?.transaction_id;
    if (!tid) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/manual-pay/${tid}/restart`);
      localStorage.setItem(TXN_KEY, data.transaction_id);
      autoGenRef.current = false; setGenError(false); setNeedsFee(null);
      setTxn(data);
      toast.success('New payment attempt started for the same bill');
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not start a new payment attempt'); }
    finally { setBusy(false); }
  };

  // Discard the WHOLE bill: cancel bill + payment attempt server-side, then wipe
  // every active reference (React state, localStorage, sessionStorage) so the old
  // bill/receipt/UTR/verification can never resurface. Only proceeds after the
  // server confirms the discard.
  const discardBill = async () => {
    const tid = txn?.transaction_id;
    setBusy(true);
    try {
      if (tid) await api.post(`/manual-pay/${tid}/discard`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not discard the bill');
      setBusy(false);
      return;
    }
    localStorage.removeItem(TXN_KEY);
    sessionStorage.removeItem('bill4pe_draft');
    autoGenRef.current = false; setGenError(false); setNeedsFee(null);
    setTxn(null); setDraft(null); setDiscardOpen(false);
    setBusy(false);
    toast.success('Bill discarded');
    nav('/app/categories');
  };

  const cancel = async () => {
    if (!txn) { nav('/app/dashboard'); return; }
    try { await api.post(`/manual-pay/${txn.transaction_id}/discard`); } catch { /* */ }
    localStorage.removeItem(TXN_KEY); sessionStorage.removeItem('bill4pe_draft');
    autoGenRef.current = false; setGenError(false);
    setTxn(null); nav('/app/dashboard');
  };

  const finishDone = () => {
    const eid = txn?.expense_id;
    localStorage.removeItem(TXN_KEY); sessionStorage.removeItem('bill4pe_draft');
    if (eid) nav(`/app/bill/${eid}`); else nav('/app/dashboard');
  };

  if (loading) return <div className="p-10 flex justify-center"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  const st = txn?.state;

  const uploadBox = (
    <div>
      <label className={`flex flex-col items-center justify-center gap-2 text-sm border-2 border-dashed rounded-xl py-8 px-4 text-center cursor-pointer hover:bg-muted/50 ${verifying ? 'opacity-70 pointer-events-none' : ''}`} data-testid="receipt-upload-label">
        {verifying ? <Loader2 className="h-6 w-6 animate-spin" /> : <ReceiptText className="h-6 w-6 text-muted-foreground" />}
        <span className="font-medium">{verifying ? 'Reading receipt & verifying payment…' : 'Upload payment receipt / screenshot'}</span>
        <span className="text-xs text-muted-foreground">PhonePe, Paytm, GPay, BHIM or bank app — amount, UTR and payee are read automatically</span>
        <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" disabled={verifying} onChange={(e) => uploadProof(e.target.files?.[0] || null)} data-testid="receipt-upload-input" />
      </label>
    </div>
  );

  return (
    <div className="max-w-lg mx-auto p-4 space-y-5" data-testid="paynow-page">
      <div className="flex items-center justify-between">
        <button onClick={() => nav(-1)} className="flex items-center gap-1 text-sm text-muted-foreground"><ArrowLeft className="h-4 w-4" /> Back</button>
        {txn && st !== 'completed' && !txn.bill_id && (
          <div className="flex items-center gap-4">
            <button onClick={startNew} disabled={busy} className="text-sm font-medium text-muted-foreground hover:text-foreground" data-testid="start-new-payment">Start new payment</button>
            <button onClick={() => setDiscardOpen(true)} disabled={busy} className="text-sm font-medium text-red-600 hover:text-red-700" data-testid="discard-bill-btn">Discard Bill &amp; Start New</button>
          </div>
        )}
      </div>

      {/* STEP 1 — bill summary → direct receipt upload (no payee questions, no QR) */}
      {!txn && (
        <>
          <div className="rounded-xl border p-4 bg-muted/30" data-testid="bill-summary">
            <div className="text-xs uppercase tracking-wider text-muted-foreground">Bill amount</div>
            <div className="text-3xl font-bold font-mono">{money(draftAmount)}</div>
            {draft?.category && <div className="text-sm text-muted-foreground mt-1">{draft.category}{draft.sub_category ? ` · ${draft.sub_category}` : ''}</div>}
          </div>
          {!draft && (
            <div className="rounded-xl border p-4" data-testid="amount-form">
              <label className="text-sm font-medium">Amount (₹)</label>
              <Input value={payeeAmount} onChange={(e) => setPayeeAmount(e.target.value.replace(/[^\d.]/g, ''))} inputMode="decimal" placeholder="0.00" className="font-mono mt-1" data-testid="payee-amount-input" />
            </div>
          )}
          <Button className="w-full" disabled={busy} onClick={startPayment} data-testid="start-payment-btn">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Upload Payment Receipt'}
          </Button>
          <p className="text-xs text-muted-foreground text-center">Pay the merchant in any UPI app, then upload the payment receipt — amount, UTR and payee are read automatically.</p>
        </>
      )}

      {/* STEP 2 — receipt upload directly (no confirm screen, no manual UTR) */}
      {(st === 'awaiting_merchant_payment' || st === 'merchant_payment_claimed') && (
        <div className="space-y-4" data-testid="proof-screen">
          <h2 className="text-xl font-semibold">Verify your payment</h2>
          <div className="rounded-xl border p-4 text-sm bg-muted/30">
            <div>Bill amount <b>{money(txn.merchant_amount)}</b></div>
            <p className="text-xs text-muted-foreground mt-1">Pay exactly this amount to the merchant in any UPI app, then upload the receipt below.</p>
          </div>
          {uploadBox}
          <p className="text-xs text-muted-foreground text-center">
            The receipt is read automatically — there is no manual UTR entry. Make sure the full receipt with amount, success status and UTR is visible.
          </p>
          {txn.verification && <VerificationCard v={txn.verification} billAmount={txn.merchant_amount} />}
        </div>
      )}

      {/* STEP 4 — verification result → fee / generate receipt */}
      {(st === 'proof_submitted' || st === 'fee_due' || st === 'fee_pending') && (
        <div className="space-y-4" data-testid="generate-screen">
          {txn.verification && <VerificationCard v={txn.verification} billAmount={txn.merchant_amount} />}
          {!verified ? (
            <div className="space-y-3" data-testid="reupload-box">
              <p className="text-sm text-muted-foreground text-center">
                We couldn't verify this payment receipt automatically. Please upload a clear, complete payment receipt.
              </p>
              {uploadBox}
            </div>
          ) : (
            <>
              <div className="rounded-xl border p-4 bg-emerald-50 text-emerald-800 text-sm flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5" /> Payment verified — <b>receipt matched</b>
              </div>
              <div className="rounded-xl border p-4 text-sm space-y-1">
                <div className="flex justify-between"><span className="text-muted-foreground">Merchant amount</span><span className="font-mono">{money(txn.merchant_amount)}</span></div>
                {isCorporate ? (
                  <div className="flex justify-between"><span className="text-muted-foreground">Convenience fee</span><span className="font-mono text-emerald-700 font-semibold">Free · Subscription</span></div>
                ) : (
                  <div className="flex justify-between"><span className="text-muted-foreground">Bill4Pe fee ({txn.platform_fee_percent}%)</span><span className="font-mono">{money(txn.platform_fee)}</span></div>
                )}
              </div>
              {isCorporate ? (
                genError ? (
                  <div className="rounded-xl border p-4 space-y-3" data-testid="auto-generate-error">
                    <div className="flex items-center gap-2 text-amber-700 text-sm"><AlertTriangle className="h-4 w-4" /> Couldn't generate the bill. Please retry.</div>
                    <Button className="w-full" disabled={busy} onClick={generate} data-testid="retry-generate-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Retry'}</Button>
                  </div>
                ) : (
                  <div className="rounded-xl border p-4 flex items-center justify-center gap-2 text-sm text-muted-foreground" data-testid="auto-generating-bill">
                    <Loader2 className="h-4 w-4 animate-spin" /> Generating your bill automatically…
                  </div>
                )
              ) : (!needsFee && (
                <Button className="w-full" disabled={busy} onClick={generate} data-testid="generate-receipt-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Generate Bill4Pe digital receipt'}</Button>
              ))}
              {needsFee && (
                <div className="rounded-xl border p-4 space-y-3" data-testid="fee-due-box">
                  <div className="flex items-center gap-2 text-amber-700 text-sm"><AlertTriangle className="h-4 w-4" /> Service fee due</div>
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Wallet balance</span><span className="font-mono">{money(needsFee.wallet_balance)}</span></div>
                  <div className="flex justify-between text-sm"><span className="text-muted-foreground">Amount due</span><span className="font-mono">{money(needsFee.fee)}</span></div>
                  <Button className="w-full" disabled={busy} onClick={payFeeRazorpay} data-testid="pay-fee-btn">Pay {money(needsFee.fee)} (service fee)</Button>
                  <Button variant="outline" className="w-full" onClick={() => nav('/app/wallet')} data-testid="add-money-btn">Add money to wallet</Button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* STEP 5 — done */}
      {(st === 'completed' || txn?.bill_id) && (
        <div className="space-y-4 text-center" data-testid="receipt-done">
          <CheckCircle2 className="h-14 w-14 text-emerald-600 mx-auto" />
          <h2 className="text-2xl font-bold">Receipt generated</h2>
          <p className="text-muted-foreground">Bill ID <span className="font-mono">{txn.bill_id}</span></p>
          <Button className="w-full" onClick={finishDone} data-testid="view-receipt-btn">View receipt</Button>
        </div>
      )}

      {/* Discard confirmation */}
      {discardOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => setDiscardOpen(false)} />
          <div className="relative bg-background rounded-xl border p-5 w-full max-w-sm space-y-4" data-testid="discard-confirm-modal">
            <div>
              <h3 className="font-semibold text-lg">Discard this bill?</h3>
              <p className="text-sm text-muted-foreground mt-1">This will cancel the current bill and payment attempt. You can create a new bill after this.</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => setDiscardOpen(false)} data-testid="discard-keep-btn">Keep Bill</Button>
              <Button variant="destructive" className="flex-1" disabled={busy} onClick={discardBill} data-testid="discard-confirm-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Discard & Start New'}</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
