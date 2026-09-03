import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Copy, ShieldCheck, AlertTriangle, Loader2, CheckCircle2, XCircle, ArrowLeft, ReceiptText } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import api from '@/lib/api';
import { openRazorpay } from '@/lib/razorpay';
import { useAuth } from '@/lib/auth';

const TXN_KEY = 'bill4pe_manual_txn';
const money = (n) => `₹${Number(n || 0).toFixed(2)}`;
const UPI_RE = /^[\w.-]{2,}@[\w.-]{2,}$/;

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
        <CheckRow label="Receiver Match" value={v.receiver_matched === true ? 'Matched' : v.receiver_matched === false ? 'Mismatch' : 'Not on receipt'} ok={v.receiver_matched} />
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
  const [payeeName, setPayeeName] = useState('');
  const [payeeUpi, setPayeeUpi] = useState('');
  const [payeeAmount, setPayeeAmount] = useState('');

  // Load draft + resume any pending transaction (app-close recovery).
  const refresh = useCallback(async (tid) => {
    try { const { data } = await api.get(`/manual-pay/${tid}`); setTxn(data); return data; }
    catch { localStorage.removeItem(TXN_KEY); setTxn(null); return null; }
  }, []);

  // Only these money-sensitive states are worth auto-resuming (user already told
  // us they paid the merchant, so we must not lose the proof/fee/receipt step).
  const RESUMABLE = ['merchant_payment_claimed', 'proof_submitted', 'fee_due', 'fee_pending'];

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
            setTxn(data); // resume the in-progress, money-sensitive payment
          } else {
            if (data && ['second_qr_required', 'awaiting_merchant_payment'].includes(data.state)) {
              api.post(`/manual-pay/${tid}/cancel`).catch(() => {});
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

  const startPayment = async () => {
    const upi = payeeUpi.trim().toLowerCase().replace(/\s+/g, '');
    if (!UPI_RE.test(upi)) { toast.error('Enter a valid UPI ID like name@bank'); return; }
    const amt = draft ? undefined : Number(payeeAmount);
    if (!draft && (!amt || amt <= 0)) { toast.error('Enter the payment amount'); return; }
    setBusy(true);
    try {
      const { data } = await api.post('/manual-pay/first-scan', {
        payee_upi: upi, payee_name: payeeName.trim() || null,
        merchant_amount: amt,
        expense_draft: draft || undefined,
      });
      localStorage.setItem(TXN_KEY, data.transaction_id);
      setTxn(data);
      toast.success(`Payee locked: ${data.payee_name || data.payee_upi}`);
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not start payment'); }
    finally { setBusy(false); }
  };

  const confirm = async (completed) => {
    setBusy(true);
    try { const { data } = await api.post(`/manual-pay/${txn.transaction_id}/confirm`, { completed }); setTxn(data); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
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

  // Abandon the current (unpaid) session and begin a brand-new payment.
  const startNew = async () => {
    const tid = txn?.transaction_id;
    if (tid) { try { await api.post(`/manual-pay/${tid}/cancel`); } catch { /* */ } }
    localStorage.removeItem(TXN_KEY);
    autoGenRef.current = false; setGenError(false);
    setTxn(null); setNeedsFee(null);
    toast.message('Starting a new payment');
  };

  const cancel = async () => {
    if (!txn) { nav('/app/dashboard'); return; }
    try { await api.post(`/manual-pay/${txn.transaction_id}/cancel`); } catch { /* */ }
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
          <button onClick={startNew} className="text-sm font-medium text-red-600" data-testid="start-new-payment">Start new payment</button>
        )}
      </div>

      {/* STEP 1 — bill summary + payee details (no QR scan, no manual refs) */}
      {!txn && (
        <>
          <div className="rounded-xl border p-4 bg-muted/30" data-testid="bill-summary">
            <div className="text-xs uppercase tracking-wider text-muted-foreground">Bill amount</div>
            <div className="text-3xl font-bold font-mono">{money(draftAmount)}</div>
            {draft?.category && <div className="text-sm text-muted-foreground mt-1">{draft.category}{draft.sub_category ? ` · ${draft.sub_category}` : ''}</div>}
          </div>
          <div className="rounded-xl border p-4 space-y-3" data-testid="payee-form">
            <div>
              <h2 className="text-xl font-semibold">Who are you paying?</h2>
              <p className="text-sm text-muted-foreground mt-1">Pay the merchant in any UPI app, then upload the payment receipt here — we verify it automatically.</p>
            </div>
            <div>
              <label className="text-sm font-medium">Merchant / payee name (optional)</label>
              <Input value={payeeName} onChange={(e) => setPayeeName(e.target.value)} placeholder="e.g. Sharma Tea Stall" data-testid="payee-name-input" />
            </div>
            <div>
              <label className="text-sm font-medium">Merchant UPI ID</label>
              <Input value={payeeUpi} onChange={(e) => setPayeeUpi(e.target.value)} placeholder="name@bank" className="font-mono" data-testid="payee-upi-input" />
            </div>
            {!draft && (
              <div>
                <label className="text-sm font-medium">Amount (₹)</label>
                <Input value={payeeAmount} onChange={(e) => setPayeeAmount(e.target.value.replace(/[^\d.]/g, ''))} inputMode="decimal" placeholder="0.00" className="font-mono" data-testid="payee-amount-input" />
              </div>
            )}
            <Button className="w-full" disabled={busy} onClick={startPayment} data-testid="start-payment-btn">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Continue'}
            </Button>
          </div>
        </>
      )}

      {/* STEP 2 — pay the merchant in your own UPI app */}
      {st === 'awaiting_merchant_payment' && (
        <div className="space-y-4" data-testid="ready-to-pay">
          <div className="rounded-xl border p-4">
            <div className="flex items-center gap-2 text-emerald-600 text-sm font-medium"><ShieldCheck className="h-4 w-4" /> Payee locked</div>
            <div className="mt-3 text-sm text-muted-foreground">Merchant</div>
            <div className="text-lg font-semibold" data-testid="rtp-merchant">{txn.payee_name || 'UPI Payee'}</div>
            <div className="text-sm font-mono">{txn.payee_upi}</div>
            <div className="mt-3 text-sm text-muted-foreground">Bill amount</div>
            <div className="text-2xl font-bold font-mono" data-testid="rtp-amount">{money(txn.merchant_amount)}</div>
          </div>
          <div className="rounded-xl border p-4 text-sm space-y-1 bg-muted/30">
            <p className="font-medium">Now pay this merchant using your preferred UPI app:</p>
            <ol className="list-decimal ml-5 text-muted-foreground space-y-0.5">
              <li>Open Google Pay, PhonePe, Paytm, BHIM or your bank app.</li>
              <li>Pay to the UPI ID above.</li>
              <li>Pay exactly {money(txn.merchant_amount)}.</li>
              <li>Return to Bill4Pe and upload the payment receipt.</li>
            </ol>
          </div>
          <Button variant="outline" className="w-full" data-testid="copy-upi-btn" onClick={() => { navigator.clipboard?.writeText(txn.payee_upi); toast.success('UPI ID copied'); }}>
            <Copy className="h-4 w-4 mr-1" /> Copy UPI ID
          </Button>
          <div className="rounded-xl border p-4">
            <p className="font-medium text-center">Did you complete the payment?</p>
            <div className="flex gap-2 mt-3">
              <Button className="flex-1" disabled={busy} onClick={() => confirm(true)} data-testid="payment-done-btn">Yes, payment done</Button>
              <Button variant="outline" className="flex-1" disabled={busy} onClick={() => toast.message('No problem — pay the merchant, then tap "Yes, payment done".')} data-testid="not-yet-btn">Not yet</Button>
            </div>
            <button className="w-full text-xs text-muted-foreground mt-3" onClick={cancel} data-testid="cancel-session-btn">Cancel payment session</button>
          </div>
        </div>
      )}

      {/* STEP 3 — receipt upload (no manual UTR entry) */}
      {st === 'merchant_payment_claimed' && (
        <div className="space-y-4" data-testid="proof-screen">
          <h2 className="text-xl font-semibold">Verify your payment</h2>
          <div className="rounded-xl border p-4 text-sm bg-muted/30">
            <div>Paid to <b>{txn.payee_name || txn.payee_upi}</b></div>
            <div className="font-mono text-muted-foreground">{txn.payee_upi}</div>
            <div className="mt-1">Amount <b>{money(txn.merchant_amount)}</b></div>
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
    </div>
  );
}
