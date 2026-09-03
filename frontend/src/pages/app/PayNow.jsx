import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import jsQR from 'jsqr';
import { Camera, Copy, ShieldCheck, AlertTriangle, Upload, Loader2, CheckCircle2, ArrowLeft } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import api from '@/lib/api';
import { openRazorpay } from '@/lib/razorpay';
import { useAuth } from '@/lib/auth';

const TXN_KEY = 'bill4pe_manual_txn';

// Strict UPI QR parser — only accept valid upi: payment QRs (spec §19/§20).
function parseUpi(raw) {
  try {
    if (!/^upi:\/\//i.test(raw || '')) return null;
    const q = raw.split('?')[1] || '';
    const p = Object.fromEntries(new URLSearchParams(q));
    const upi = (p.pa || '').trim();
    if (!upi || !/^[\w.-]{2,}@[\w.-]{2,}$/.test(upi)) return null;
    return { upi, name: decodeURIComponent(p.pn || '').trim(), amt: p.am || '' };
  } catch { return null; }
}

const money = (n) => `₹${Number(n || 0).toFixed(2)}`;

// ---- Reusable QR scanner (camera + image upload + manual entry) ----
function QrScanner({ title, hint, onResult, onCancel }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const rafRef = useRef(null);
  const decodedRef = useRef(false);
  const [status, setStatus] = useState('starting');
  const [err, setErr] = useState('');
  const [manualUpi, setManualUpi] = useState('');
  const [manualName, setManualName] = useState('');

  const stop = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    const v = videoRef.current;
    if (v && v.srcObject) { v.srcObject.getTracks().forEach((t) => t.stop()); v.srcObject = null; }
  }, []);

  const handle = useCallback((data) => {
    if (decodedRef.current) return;
    const parsed = parseUpi(data);
    if (!parsed) { setErr('Not a valid UPI payment QR. Scan a UPI QR or enter the UPI ID below.'); return; }
    decodedRef.current = true;
    stop();
    onResult(parsed);
  }, [onResult, stop]);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
        if (!active) { stream.getTracks().forEach((t) => t.stop()); return; }
        const v = videoRef.current; v.srcObject = stream; await v.play(); setStatus('running');
        const tick = () => {
          if (!active || decodedRef.current) return;
          const v2 = videoRef.current, c = canvasRef.current;
          if (v2 && c && v2.videoWidth) {
            const w = v2.videoWidth, h = v2.videoHeight; c.width = w; c.height = h;
            const ctx = c.getContext('2d'); ctx.drawImage(v2, 0, 0, w, h);
            const img = ctx.getImageData(0, 0, w, h);
            const r = jsQR(img.data, w, h, { inversionAttempts: 'attemptBoth' });
            if (r?.data) handle(r.data);
          }
          rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
      } catch (e) {
        setStatus('error');
        setErr(e?.name === 'NotAllowedError' ? 'Camera permission denied. Enter the UPI ID below.' : 'Could not open camera. Enter the UPI ID below.');
      }
    })();
    return () => { active = false; stop(); };
  }, [handle, stop]);

  const onFile = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    try {
      const img = new Image(); const url = URL.createObjectURL(file);
      await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
      const c = canvasRef.current; c.width = img.width; c.height = img.height;
      const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0);
      const d = ctx.getImageData(0, 0, img.width, img.height);
      const r = jsQR(d.data, img.width, img.height, { inversionAttempts: 'attemptBoth' });
      URL.revokeObjectURL(url);
      if (r?.data) handle(r.data); else setErr('No UPI QR found in that image.');
    } catch { setErr('Could not read that image.'); }
  };

  const submitManual = () => {
    const parsed = parseUpi(`upi://pay?pa=${encodeURIComponent(manualUpi.trim())}&pn=${encodeURIComponent(manualName.trim())}`);
    if (!parsed) { toast.error('Enter a valid UPI ID like name@bank'); return; }
    decodedRef.current = true; stop(); onResult(parsed);
  };

  return (
    <div className="space-y-4" data-testid="qr-scanner">
      <div>
        <h2 className="text-xl font-semibold">{title}</h2>
        {hint && <p className="text-sm text-muted-foreground mt-1">{hint}</p>}
      </div>
      <div className="relative rounded-2xl overflow-hidden bg-black aspect-square max-w-sm mx-auto border border-border">
        <video ref={videoRef} playsInline muted className="w-full h-full object-cover" />
        <canvas ref={canvasRef} className="hidden" />
        {status !== 'running' && (
          <div className="absolute inset-0 flex items-center justify-center text-white/80 text-sm">
            {status === 'starting' ? <Loader2 className="h-6 w-6 animate-spin" /> : <Camera className="h-8 w-8" />}
          </div>
        )}
      </div>
      {err && <p className="text-sm text-red-600 text-center" data-testid="scan-error">{err}</p>}
      <div className="max-w-sm mx-auto space-y-2">
        <label className="flex items-center justify-center gap-2 text-sm border border-dashed rounded-xl py-2 cursor-pointer hover:bg-muted/50">
          <Upload className="h-4 w-4" /> Upload QR image
          <input type="file" accept="image/*" className="hidden" onChange={onFile} data-testid="scan-upload" />
        </label>
        <div className="text-center text-xs text-muted-foreground">or enter UPI ID manually</div>
        <Input placeholder="merchant name (optional)" value={manualName} onChange={(e) => setManualName(e.target.value)} data-testid="manual-upi-name" />
        <Input placeholder="name@bank" value={manualUpi} onChange={(e) => setManualUpi(e.target.value)} data-testid="manual-upi-input" />
        <div className="flex gap-2">
          <Button className="flex-1" onClick={submitManual} data-testid="manual-upi-submit">Use this UPI</Button>
          {onCancel && <Button variant="outline" onClick={() => { stop(); onCancel(); }} data-testid="scan-cancel">Cancel</Button>}
        </div>
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
  const [utrFull, setUtrFull] = useState('');
  const [utrLast4, setUtrLast4] = useState('');
  const [screenshot, setScreenshot] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const [needsFee, setNeedsFee] = useState(null);

  // Load draft + resume any pending transaction (app-close recovery, spec §35).
  const refresh = useCallback(async (tid) => {
    try { const { data } = await api.get(`/manual-pay/${tid}`); setTxn(data); return data; }
    catch { localStorage.removeItem(TXN_KEY); setTxn(null); return null; }
  }, []);

  // Only these money-sensitive states are worth auto-resuming (user already told
  // us they paid the merchant, so we must not lose the proof/fee/receipt step).
  // Anything earlier (just scanned, not yet paid) is treated as abandoned so a
  // NEW payment always starts fresh instead of re-opening the old vendor.
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
            // Early (only-scanned) or already-completed/cancelled → don't force the
            // old vendor. Best-effort cancel the abandoned session, then start fresh.
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

  const doFirstScan = async (parsed) => {
    setBusy(true);
    try {
      const { data } = await api.post('/manual-pay/first-scan', {
        payee_upi: parsed.upi, payee_name: parsed.name || null,
        merchant_amount: draft ? undefined : Number(parsed.amt) || undefined,
        expense_draft: draft || undefined,
      });
      localStorage.setItem(TXN_KEY, data.transaction_id);
      setTxn(data);
      toast.success(`Merchant locked: ${data.payee_name || data.payee_upi}`);
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not start payment'); }
    finally { setBusy(false); }
  };

  const confirm = async (completed) => {
    setBusy(true);
    try { const { data } = await api.post(`/manual-pay/${txn.transaction_id}/confirm`, { completed }); setTxn(data); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  // When a payment screenshot is chosen, auto-read the 12-digit UTR with Gemini
  // so the user doesn't have to type it. Falls back to manual entry on failure.
  const onScreenshot = async (file) => {
    setScreenshot(file || null);
    if (!file) return;
    setExtracting(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post('/ai/extract-utr', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      if (data?.found && data?.utr) {
        setUtrFull(String(data.utr).replace(/\D/g, '').slice(0, 12));
        toast.success('UTR auto-filled from screenshot ✓');
      } else {
        toast.message("Couldn't read the UTR — please type the 12-digit UTR.");
      }
    } catch (e) {
      toast.message(e.response?.data?.detail || "Couldn't read the UTR — please type it.");
    } finally {
      setExtracting(false);
    }
  };

  const submitProof = async () => {
    if (utrFull && utrFull.length !== 12) { toast.error('UTR number must be exactly 12 digits'); return; }
    if (!utrFull && !utrLast4 && !screenshot) { toast.error('Enter a UTR, last 4 digits, or upload a screenshot'); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      if (utrFull) fd.append('utr_full', utrFull);
      if (utrLast4) fd.append('utr_last4', utrLast4);
      if (screenshot) fd.append('screenshot', screenshot);
      const { data } = await api.post(`/manual-pay/${txn.transaction_id}/proof`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setTxn(data); toast.success('Payment proof saved ✓');
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not save proof'); }
    finally { setBusy(false); }
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

  // Corporate = monthly subscription (unlimited, no fee) -> generate the bill
  // AUTOMATICALLY once payment proof is in, with no manual "generate" prompt.
  useEffect(() => {
    if (!isCorporate) return;
    const state = txn?.state;
    const ready = state === 'proof_submitted' || state === 'fee_due' || state === 'fee_pending';
    if (ready && !txn?.bill_id && !busy && !autoGenRef.current) {
      autoGenRef.current = true;
      generate();
    }
  }, [txn, isCorporate, busy]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Abandon the current (unpaid) session and begin a brand-new payment — used
  // when the user actually wants to pay a different vendor.
  const startNew = async () => {
    const tid = txn?.transaction_id;
    if (tid) { try { await api.post(`/manual-pay/${tid}/cancel`); } catch { /* */ } }
    localStorage.removeItem(TXN_KEY);
    autoGenRef.current = false; setGenError(false);
    setTxn(null); setNeedsFee(null); setUtrFull(''); setUtrLast4(''); setScreenshot(null);
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

  return (
    <div className="max-w-lg mx-auto p-4 space-y-5" data-testid="paynow-page">
      <div className="flex items-center justify-between">
        <button onClick={() => nav(-1)} className="flex items-center gap-1 text-sm text-muted-foreground"><ArrowLeft className="h-4 w-4" /> Back</button>
        {txn && st !== 'completed' && !txn.bill_id && (
          <button onClick={startNew} className="text-sm font-medium text-red-600" data-testid="start-new-payment">Start new payment</button>
        )}
      </div>

      {/* STEP 1 — single QR scan */}
      {!txn && (
        <>
          <div className="rounded-xl border p-4 bg-muted/30" data-testid="bill-summary">
            <div className="text-xs uppercase tracking-wider text-muted-foreground">Bill amount</div>
            <div className="text-3xl font-bold font-mono">{money(draftAmount)}</div>
            {draft?.category && <div className="text-sm text-muted-foreground mt-1">{draft.category}{draft.sub_category ? ` · ${draft.sub_category}` : ''}</div>}
          </div>
          <QrScanner title="Scan merchant QR" hint="Scan the merchant's UPI QR once to continue." onResult={doFirstScan} onCancel={() => nav('/app/dashboard')} />
        </>
      )}

      {/* STEP 2 — ready to pay merchant directly (single scan) */}
      {st === 'awaiting_merchant_payment' && (
        <div className="space-y-4" data-testid="ready-to-pay">
          <div className="rounded-xl border p-4">
            <div className="flex items-center gap-2 text-emerald-600 text-sm font-medium"><ShieldCheck className="h-4 w-4" /> QR Verified</div>
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
              <li>Scan the merchant's QR / pay to the UPI ID above.</li>
              <li>Pay exactly {money(txn.merchant_amount)}.</li>
              <li>Return to Bill4Pe.</li>
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

      {/* STEP 4 — payment proof */}
      {st === 'merchant_payment_claimed' && (
        <div className="space-y-4" data-testid="proof-screen">
          <h2 className="text-xl font-semibold">Payment proof</h2>
          <div className="rounded-xl border p-4 text-sm bg-muted/30">
            <div>Paid to <b>{txn.payee_name || txn.payee_upi}</b></div>
            <div className="font-mono text-muted-foreground">{txn.payee_upi}</div>
            <div className="mt-1">Amount <b>{money(txn.merchant_amount)}</b></div>
          </div>
          <div>
            <label className="text-sm font-medium">UPI Transaction ID / UTR (12 digits)</label>
            <Input value={utrFull} onChange={(e) => setUtrFull(e.target.value.replace(/\D/g, '').slice(0, 12))} maxLength={12} inputMode="numeric" placeholder="12-digit UTR e.g. 401234567890" data-testid="utr-full-input" />
            <p className="text-xs text-muted-foreground mt-1" data-testid="utr-digit-count">{utrFull.length}/12 digits</p>
          </div>
          <div>
            <label className="text-sm font-medium">Or last 4 digits</label>
            <Input value={utrLast4} onChange={(e) => setUtrLast4(e.target.value.replace(/\D/g, '').slice(0, 4))} placeholder="1234" data-testid="utr-last4-input" />
          </div>
          <label className={`flex items-center justify-center gap-2 text-sm border border-dashed rounded-xl py-3 cursor-pointer hover:bg-muted/50 ${extracting ? 'opacity-70 pointer-events-none' : ''}`} data-testid="screenshot-label">
            {extracting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {extracting ? 'Reading UTR from screenshot…' : (screenshot ? screenshot.name : 'Upload payment screenshot to auto-read UTR')}
            <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" disabled={extracting} onChange={(e) => onScreenshot(e.target.files?.[0] || null)} data-testid="screenshot-input" />
          </label>
          <Button className="w-full" disabled={busy} onClick={submitProof} data-testid="submit-proof-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Submit proof'}</Button>
        </div>
      )}

      {/* STEP 5 — proof saved → generate receipt (+ fee) */}
      {(st === 'proof_submitted' || st === 'fee_due' || st === 'fee_pending') && (
        <div className="space-y-4" data-testid="generate-screen">
          <div className="rounded-xl border p-4 bg-emerald-50 text-emerald-800 text-sm flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5" /> Payment details saved — <b>Confirmed by user</b>
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
              <Button className="w-full" disabled={busy} onClick={payFeeRazorpay} data-testid="pay-fee-btn">Pay {money(needsFee.fee)} (Bill4Pe Fee QR)</Button>
              <Button variant="outline" className="w-full" onClick={() => nav('/app/wallet')} data-testid="add-money-btn">Add money to wallet</Button>
            </div>
          )}
        </div>
      )}

      {/* STEP 6 — done */}
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
