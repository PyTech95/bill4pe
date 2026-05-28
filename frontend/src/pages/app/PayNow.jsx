import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Html5Qrcode } from 'html5-qrcode';
import { QrCode, CheckCircle2, Smartphone, MapPin, Loader2, RefreshCw, Camera, AlertCircle, KeyRound, ExternalLink, Copy } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import api from '@/lib/api';
import { useAuth } from '@/lib/auth';

const parseUpi = (data) => {
  // upi://pay?pa=xxx@bank&pn=Name&am=10&...
  try {
    if (!data?.toLowerCase().startsWith('upi://')) return { upi: '', name: '', amt: '' };
    const q = data.split('?')[1] || '';
    const params = Object.fromEntries(new URLSearchParams(q));
    return { upi: params.pa || '', name: decodeURIComponent(params.pn || ''), amt: params.am || '' };
  } catch { return { upi: '', name: '', amt: '' }; }
};

// Detect in-app webviews (WhatsApp/Instagram/Facebook/Twitter etc.) which on iOS block getUserMedia silently.
const detectInAppBrowser = () => {
  if (typeof navigator === 'undefined') return { isInApp: false, isIOS: false, name: '' };
  const ua = navigator.userAgent || '';
  const isIOS = /iPhone|iPad|iPod/i.test(ua);
  const isAndroid = /Android/i.test(ua);
  let name = '';
  if (/FBAN|FBAV|FB_IAB/i.test(ua)) name = 'Facebook';
  else if (/Instagram/i.test(ua)) name = 'Instagram';
  else if (/Twitter/i.test(ua)) name = 'Twitter / X';
  else if (/Line\//i.test(ua)) name = 'LINE';
  else if (/MicroMessenger/i.test(ua)) name = 'WeChat';
  // WhatsApp on iOS leaves no obvious UA token; flag iOS WKWebView (no Safari token) as suspect
  const isIosSuspectWebView = isIOS && !/Safari/i.test(ua) && !/CriOS|FxiOS|EdgiOS/i.test(ua);
  if (!name && isIosSuspectWebView) name = 'WhatsApp / In-app browser';
  // Android WhatsApp UA contains "wv" (WebView)
  if (!name && isAndroid && /; wv\)/i.test(ua)) name = 'In-app browser';
  return { isInApp: !!name, isIOS, isAndroid, name };
};

export default function PayNow() {
  const nav = useNavigate();
  const { refreshUser } = useAuth();
  const [draft, setDraft] = useState(null);
  const [stage, setStage] = useState('scan'); // scan | confirm | submitting
  const [merchant, setMerchant] = useState({ name: '', upi: '', mobile: '', txnId: '', method: 'UPI' });
  const [geo, setGeo] = useState({ lat: null, lng: null });
  const [cameras, setCameras] = useState([]);
  const [activeCamIdx, setActiveCamIdx] = useState(0);
  const [scanStatus, setScanStatus] = useState('starting'); // starting | running | error | denied | inapp
  const [scanError, setScanError] = useState('');
  const [browserInfo] = useState(() => detectInAppBrowser());
  const scannerRef = useRef(null);
  const startedRef = useRef(false);
  const probeTimerRef = useRef(null);

  useEffect(() => {
    try {
      const d = JSON.parse(sessionStorage.getItem('bill4pe_draft') || 'null');
      if (!d) { nav('/app'); return; }
      setDraft(d);
      // Pre-fill merchant for quick-pay flow
      if (d.prefill_merchant) {
        setMerchant((m) => ({
          ...m,
          name: d.prefill_merchant.merchant_name || '',
          upi: d.prefill_merchant.merchant_upi || '',
        }));
        setStage('confirm');
      }
    } catch { nav('/app'); }

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (p) => setGeo({ lat: p.coords.latitude, lng: p.coords.longitude }),
        () => { /* user denied — non-blocking */ }
      );
    }
  }, [nav]);

  const total = (draft?.items || []).reduce((s, i) => s + i.quantity * i.unit_price, 0);

  // Robust camera lifecycle: enumerate → pick back camera → start
  useEffect(() => {
    if (stage !== 'scan' || startedRef.current) return;
    const el = document.getElementById('qr-reader');
    if (!el) return;
    startedRef.current = true;
    let cancelled = false;
    let q = null;

    const startScanner = async () => {
      setScanStatus('starting');
      setScanError('');

      // Hard-stop probe after 9s — covers iOS in-app WebViews that never reject getUserMedia
      probeTimerRef.current = setTimeout(() => {
        if (cancelled) return;
        setScanStatus('inapp');
        setScanError(
          browserInfo.isInApp
            ? `${browserInfo.name} se camera nahin chalega. Safari/Chrome me kholiye, ya neeche UPI manually enter kariye.`
            : 'Camera response nahin de raha. Neeche UPI manually enter kariye.'
        );
      }, 9000);

      try {
        // Probe permission early: triggers permission prompt and unlocks getCameras()
        if (navigator.mediaDevices?.getUserMedia) {
          const probe = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
          probe.getTracks().forEach((t) => t.stop());
        } else {
          throw new Error('getUserMedia not supported');
        }
      } catch (err) {
        if (cancelled) return;
        if (probeTimerRef.current) { clearTimeout(probeTimerRef.current); probeTimerRef.current = null; }
        const denied = err && (err.name === 'NotAllowedError' || err.name === 'SecurityError');
        const isInApp = browserInfo.isInApp;
        setScanStatus(isInApp ? 'inapp' : (denied ? 'denied' : 'error'));
        setScanError(
          isInApp
            ? `${browserInfo.name} se camera nahin chalega. Safari/Chrome me kholiye, ya neeche UPI manually enter kariye.`
            : denied
            ? 'Camera permission denied. Allow camera access from browser settings, or enter UPI manually.'
            : `Camera unavailable: ${err?.message || err?.name || 'unknown'}. Enter UPI manually below.`
        );
        return;
      }

      let camList = [];
      try {
        camList = await Html5Qrcode.getCameras();
      } catch (err) {
        if (cancelled) return;
        setScanStatus('error');
        setScanError('Could not access cameras. Enter UPI manually.');
        return;
      }
      if (!camList || !camList.length) {
        setScanStatus('error');
        setScanError('No camera detected on this device. Enter UPI manually.');
        return;
      }
      if (cancelled) return;
      setCameras(camList);

      // Prefer a back/environment camera
      const back = camList.find((c) => /back|rear|environment/i.test(c.label));
      const idx = back ? camList.indexOf(back) : (camList.length > 1 ? camList.length - 1 : 0);
      setActiveCamIdx(idx);

      try {
        q = new Html5Qrcode('qr-reader', { verbose: false });
        scannerRef.current = q;
        await q.start(
          camList[idx].id,
          {
            fps: 10,
            qrbox: (vw, vh) => {
              const min = Math.floor(Math.min(vw, vh) * 0.7);
              return { width: min, height: min };
            },
            aspectRatio: 1,
            videoConstraints: { facingMode: 'environment' },
          },
          (decoded) => {
            const parsed = parseUpi(decoded);
            setMerchant((m) => ({
              ...m,
              upi: parsed.upi || decoded.slice(0, 100),
              name: parsed.name || m.name,
            }));
            q.stop().catch(() => {}).then(() => setStage('confirm'));
          },
          () => { /* ignore per-frame scan misses */ }
        );
        if (probeTimerRef.current) { clearTimeout(probeTimerRef.current); probeTimerRef.current = null; }
        if (!cancelled) setScanStatus('running');
      } catch (err) {
        if (cancelled) return;
        if (probeTimerRef.current) { clearTimeout(probeTimerRef.current); probeTimerRef.current = null; }
        setScanStatus('error');
        setScanError(`Camera failed to start: ${err?.message || err?.name || 'unknown error'}. Enter UPI manually.`);
      }
    };

    startScanner();

    return () => {
      cancelled = true;
      if (probeTimerRef.current) { clearTimeout(probeTimerRef.current); probeTimerRef.current = null; }
      try {
        if (scannerRef.current) {
          scannerRef.current.stop().catch(() => {}).finally(() => {
            try { scannerRef.current.clear(); } catch { /* */ }
            scannerRef.current = null;
          });
        }
      } catch { /* ignore */ }
      startedRef.current = false;
    };
  }, [stage]);

  const switchCamera = async () => {
    if (cameras.length < 2 || !scannerRef.current) return;
    const nextIdx = (activeCamIdx + 1) % cameras.length;
    try {
      await scannerRef.current.stop();
      await scannerRef.current.start(
        cameras[nextIdx].id,
        { fps: 10, qrbox: (vw, vh) => { const m = Math.floor(Math.min(vw, vh) * 0.7); return { width: m, height: m }; }, aspectRatio: 1 },
        (decoded) => {
          const parsed = parseUpi(decoded);
          setMerchant((m) => ({
            ...m,
            upi: parsed.upi || decoded.slice(0, 100),
            name: parsed.name || m.name,
          }));
          scannerRef.current.stop().catch(() => {}).then(() => setStage('confirm'));
        },
        () => { /* */ }
      );
      setActiveCamIdx(nextIdx);
    } catch (err) {
      toast.error('Could not switch camera');
    }
  };

  const skipScan = async () => {
    try { await scannerRef.current?.stop(); } catch { /* ignore */ }
    if (probeTimerRef.current) { clearTimeout(probeTimerRef.current); probeTimerRef.current = null; }
    setStage('confirm');
  };

  const openInExternalBrowser = async () => {
    const url = window.location.href;
    try {
      await navigator.clipboard?.writeText(url);
      toast.success('Link copied — paste it in Safari/Chrome');
    } catch {
      toast.info('Copy this link and open in Safari/Chrome');
    }
    // Best-effort: try x-safari (works only when not in iOS WKWebView restrictions but harmless)
    try { window.open(url, '_blank', 'noopener,noreferrer'); } catch { /* ignore */ }
  };

  const buildUpiLink = (scheme = 'upi') => {
    const params = new URLSearchParams({
      pa: merchant.upi,
      pn: merchant.name || 'Merchant',
      am: total.toFixed(2),
      cu: 'INR',
      tn: 'BILL4PE Expense',
    });
    return `${scheme}://pay?${params.toString()}`;
  };

  const launchUpiApp = (scheme = 'upi') => {
    if (!merchant.upi) { toast.error('Merchant UPI ID required'); return; }
    const link = buildUpiLink(scheme);
    // Anchor-click is more reliable on iOS Safari than location.href for custom schemes
    try {
      const a = document.createElement('a');
      a.href = link;
      a.rel = 'noopener';
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { try { document.body.removeChild(a); } catch { /* */ } }, 200);
    } catch {
      window.location.href = link;
    }
    // Soft hint after a short delay (in case UPI app didn't open)
    setTimeout(() => {
      toast.info('App nahin khula? Niche se UPI ID copy karke GPay/PhonePe me paste kariye.', { duration: 5000 });
    }, 2200);
  };

  const copyUpiId = async () => {
    if (!merchant.upi) { toast.error('Merchant UPI ID required'); return; }
    try {
      await navigator.clipboard.writeText(merchant.upi);
      toast.success(`UPI ID copied: ${merchant.upi}`);
    } catch {
      toast.info(`UPI ID: ${merchant.upi}`);
    }
  };

  const submit = async () => {
    if (!merchant.name?.trim() || !merchant.upi?.trim()) { toast.error('Merchant Name & UPI required'); return; }
    if (!merchant.txnId?.trim()) { toast.error('Enter Transaction ID after paying'); return; }
    setStage('submitting');
    try {
      const payload = {
        category: draft.category,
        sub_category: draft.sub_category,
        items: draft.items,
        notes: draft.notes || '',
        payment: {
          merchant_name: merchant.name,
          merchant_upi: merchant.upi,
          merchant_mobile: merchant.mobile,
          transaction_id: merchant.txnId,
          amount: total,
          latitude: geo.lat,
          longitude: geo.lng,
          payment_method: merchant.method,
          ...(draft.trip_meta ? { trip: draft.trip_meta } : {}),
          ...(draft.stay_meta ? { stay: draft.stay_meta } : {}),
        },
      };
      const { data } = await api.post('/expenses', payload);
      sessionStorage.removeItem('bill4pe_draft');
      await refreshUser();
      toast.success('Payment captured!');
      nav(`/app/bill/${data.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not save expense');
      setStage('confirm');
    }
  };

  if (!draft) return null;

  return (
    <div className="pb-6">
      <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Step 5</div>
      <h1 className="font-display text-2xl font-bold text-navy mt-1">Pay merchant</h1>
      <p className="text-sm text-slate-500 mt-1">
        Total: <span className="font-mono font-bold text-navy">₹ {total.toFixed(2)}</span>
      </p>

      {stage === 'scan' && (
        <div className="mt-5 space-y-4">
          {browserInfo.isInApp && (
            <div
              data-testid="inapp-warning-banner"
              className="rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 flex items-start gap-3"
            >
              <AlertCircle className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" />
              <div className="flex-1">
                <div className="text-sm font-bold text-amber-900">
                  {browserInfo.name} me camera band rehta hai
                </div>
                <div className="text-xs text-amber-800 mt-0.5 leading-snug">
                  QR scan ke liye Safari/Chrome me kholiye, ya neeche UPI manually enter kariye.
                </div>
                <button
                  onClick={openInExternalBrowser}
                  data-testid="open-external-btn"
                  className="press-down mt-2 inline-flex items-center gap-1.5 text-xs font-bold text-amber-900 underline underline-offset-2"
                >
                  <ExternalLink className="w-3.5 h-3.5" /> Copy link &amp; open in Safari
                </button>
              </div>
            </div>
          )}

          <div className="flat-card p-3 relative">
            <div
              id="qr-reader"
              className="rounded-xl overflow-hidden bg-black aspect-square relative"
              data-testid="qr-reader"
              style={{ minHeight: '280px' }}
            />

            {/* Camera status overlays */}
            {scanStatus === 'starting' && (
              <div className="absolute inset-3 rounded-xl bg-black/85 backdrop-blur-sm flex flex-col items-center justify-center text-white text-center px-6">
                <Loader2 className="w-8 h-8 animate-spin text-lime" />
                <div className="mt-3 text-xs uppercase tracking-[0.25em] font-bold">Starting camera…</div>
                <div className="mt-1 text-[11px] text-white/60">Allow camera permission if prompted</div>
                <button
                  onClick={skipScan}
                  data-testid="starting-manual-fallback-btn"
                  className="press-down mt-4 inline-flex items-center gap-1.5 text-[11px] text-white/80 underline underline-offset-2"
                >
                  <KeyRound className="w-3 h-3" /> Camera not opening? Enter UPI manually
                </button>
              </div>
            )}
            {(scanStatus === 'error' || scanStatus === 'denied' || scanStatus === 'inapp') && (
              <div className="absolute inset-3 rounded-xl bg-black/90 backdrop-blur-sm flex flex-col items-center justify-center text-white text-center px-5 py-4">
                <div className="w-12 h-12 rounded-full bg-red-500/15 grid place-items-center">
                  <AlertCircle className="w-6 h-6 text-red-400" />
                </div>
                <div className="mt-3 text-sm font-bold">
                  {scanStatus === 'denied'
                    ? 'Camera permission needed'
                    : scanStatus === 'inapp'
                    ? `Camera blocked in ${browserInfo.name || 'in-app browser'}`
                    : 'Camera unavailable'}
                </div>
                <div className="mt-1 text-[11px] text-white/70 leading-snug max-w-[280px]">
                  {scanError || 'Tap below to enter the merchant UPI ID manually.'}
                </div>
                <button
                  onClick={skipScan}
                  data-testid="enter-manually-btn"
                  className="press-down mt-4 inline-flex items-center gap-2 h-11 px-5 bg-lime text-navy rounded-full font-bold text-sm"
                >
                  <KeyRound className="w-4 h-4" /> Enter UPI Manually
                </button>
                {scanStatus === 'inapp' && (
                  <button
                    onClick={openInExternalBrowser}
                    data-testid="overlay-open-external-btn"
                    className="press-down mt-2 inline-flex items-center gap-1.5 text-[11px] text-white/70 underline underline-offset-2"
                  >
                    <ExternalLink className="w-3 h-3" /> Open in Safari/Chrome
                  </button>
                )}
              </div>
            )}

            {/* Camera switch button (when 2+ cams) */}
            {scanStatus === 'running' && cameras.length > 1 && (
              <button
                onClick={switchCamera}
                data-testid="switch-camera-btn"
                className="absolute top-5 right-5 z-10 w-10 h-10 grid place-items-center rounded-full bg-white/15 backdrop-blur text-white hover:bg-white/25"
                aria-label="Switch camera"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            )}
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-500 justify-center">
            <QrCode className="w-4 h-4" /> Scan GPay / PhonePe / Paytm / BharatPe / BHIM QR
          </div>
          <button
            onClick={skipScan}
            data-testid="skip-scan-btn"
            className="press-down w-full inline-flex items-center justify-center gap-2 h-12 rounded-xl border border-soft bg-white text-navy text-sm font-semibold hover:bg-slate-50"
          >
            <KeyRound className="w-4 h-4" /> Can't scan? Enter UPI ID manually
          </button>
        </div>
      )}

      {(stage === 'confirm' || stage === 'submitting') && (
        <div className="mt-5 space-y-4">
          <div className="flat-card p-5">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Merchant</div>
            <div className="mt-3 space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Name</label>
                <Input value={merchant.name} onChange={(e) => setMerchant({ ...merchant, name: e.target.value })}
                       className="mt-1 h-11 rounded-lg border-soft" data-testid="merchant-name-input" placeholder="e.g. Suresh Tiffin Centre" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">UPI ID</label>
                <Input value={merchant.upi} onChange={(e) => setMerchant({ ...merchant, upi: e.target.value })}
                       className="mt-1 h-11 rounded-lg border-soft font-mono" data-testid="merchant-upi-input" placeholder="merchant@upi" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Mobile (optional)</label>
                <Input value={merchant.mobile} onChange={(e) => setMerchant({ ...merchant, mobile: e.target.value })}
                       className="mt-1 h-11 rounded-lg border-soft font-mono" data-testid="merchant-mobile-input" placeholder="9999988888" />
              </div>
            </div>
          </div>

          <button
            onClick={() => launchUpiApp('upi')}
            data-testid="launch-upi-btn"
            className="press-down w-full bg-navy text-white rounded-2xl p-4 flex items-center justify-between hover:bg-[#152042]"
          >
            <span className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-brand text-white grid place-items-center">
                <Smartphone className="w-5 h-5" />
              </div>
              <span className="text-left">
                <div className="font-display font-bold">Open UPI App</div>
                <div className="text-xs text-white/60">Pay ₹{total.toFixed(2)} via GPay/PhonePe/Paytm</div>
              </span>
            </span>
            <CheckCircle2 className="w-5 h-5 text-brand" />
          </button>

          {/* App-specific fallbacks + copy UPI for users where upi:// doesn't open the chooser */}
          <div className="grid grid-cols-3 gap-2">
            <button
              onClick={() => launchUpiApp('tez')}
              data-testid="launch-gpay-btn"
              className="press-down h-11 rounded-xl bg-white border-2 border-soft text-navy text-xs font-bold"
            >
              GPay
            </button>
            <button
              onClick={() => launchUpiApp('phonepe')}
              data-testid="launch-phonepe-btn"
              className="press-down h-11 rounded-xl bg-white border-2 border-soft text-navy text-xs font-bold"
            >
              PhonePe
            </button>
            <button
              onClick={() => launchUpiApp('paytmmp')}
              data-testid="launch-paytm-btn"
              className="press-down h-11 rounded-xl bg-white border-2 border-soft text-navy text-xs font-bold"
            >
              Paytm
            </button>
          </div>

          <button
            onClick={copyUpiId}
            data-testid="copy-upi-id-btn"
            className="press-down w-full h-12 rounded-xl bg-lime/15 border-2 border-lime/40 text-navy font-bold text-sm inline-flex items-center justify-center gap-2"
          >
            <Copy className="w-4 h-4" />
            Copy UPI ID — paste in any UPI app
          </button>

          <div className="flat-card p-5">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">After paying</div>
            <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold mt-3 block">Transaction ID</label>
            <Input value={merchant.txnId} onChange={(e) => setMerchant({ ...merchant, txnId: e.target.value })}
                   className="mt-1 h-11 rounded-lg border-soft font-mono" data-testid="merchant-txn-input"
                   placeholder="e.g. T2402151234567890" />

            <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
              <MapPin className="w-3.5 h-3.5" />
              {geo.lat ? (
                <span className="font-mono">
                  {geo.lat.toFixed(4)}, {geo.lng.toFixed(4)} captured
                </span>
              ) : (
                <span>Location will be saved if permitted</span>
              )}
            </div>
          </div>

          <Button
            onClick={submit}
            disabled={stage === 'submitting'}
            className="press-down w-full h-12 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
            data-testid="confirm-payment-btn"
          >
            {stage === 'submitting' ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Saving...</>
            ) : 'Confirm & Save Expense'}
          </Button>
        </div>
      )}
    </div>
  );
}
