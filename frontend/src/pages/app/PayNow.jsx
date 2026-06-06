import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import jsQR from 'jsqr';
import { QrCode, CheckCircle2, Smartphone, MapPin, Loader2, RefreshCw, AlertCircle, ExternalLink, Copy } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import api from '@/lib/api';
import { useAuth } from '@/lib/auth';

const parseUpi = (data) => {
  try {
    if (!data?.toLowerCase().startsWith('upi://')) return { upi: '', name: '', amt: '' };
    const q = data.split('?')[1] || '';
    const params = Object.fromEntries(new URLSearchParams(q));
    return { upi: params.pa || '', name: decodeURIComponent(params.pn || ''), amt: params.am || '' };
  } catch { return { upi: '', name: '', amt: '' }; }
};

// Detect in-app webviews that silently block getUserMedia on iOS
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
  const isIosSuspectWebView = isIOS && !/Safari/i.test(ua) && !/CriOS|FxiOS|EdgiOS/i.test(ua);
  if (!name && isIosSuspectWebView) name = 'WhatsApp / In-app browser';
  if (!name && isAndroid && /; wv\)/i.test(ua)) name = 'In-app browser';
  return { isInApp: !!name, isIOS, isAndroid, name };
};

export default function PayNow() {
  const nav = useNavigate();
  const { refreshUser } = useAuth();
  const [draft, setDraft] = useState(null);
  const [stage, setStage] = useState('scan');
  const [merchant, setMerchant] = useState({ name: '', upi: '', mobile: '', txnId: '', method: 'UPI' });
  const [geo, setGeo] = useState({ lat: null, lng: null });
  const [scanStatus, setScanStatus] = useState('starting'); // starting | running | error | denied | inapp
  const [scanError, setScanError] = useState('');
  const [browserInfo] = useState(() => detectInAppBrowser());
  const [cameraList, setCameraList] = useState([]);
  const [currentDeviceId, setCurrentDeviceId] = useState(null);
  const [useFrontCamera, setUseFrontCamera] = useState(false);
  const [paymentInitiated, setPaymentInitiated] = useState(false);
  // Live diagnostics shown to user in error state — helps debug "black screen" in production
  const [diag, setDiag] = useState({ ready: 0, vw: 0, vh: 0, trackMuted: null, trackState: '' });

  // Native camera refs
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const rafRef = useRef(null);
  const decodedRef = useRef(false);
  const startTokenRef = useRef(0);
  const watchdogRef = useRef(null);

  // Load draft + geolocation
  useEffect(() => {
    try {
      const d = JSON.parse(sessionStorage.getItem('bill4pe_draft') || 'null');
      if (!d) { nav('/app'); return; }
      setDraft(d);
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
        () => { /* non-blocking */ }
      );
    }
  }, [nav]);

  const total = (draft?.items || []).reduce((s, i) => s + i.quantity * i.unit_price, 0);

  // Stop camera + cancel rAF loop + clear watchdog
  const stopCamera = useCallback(() => {
    if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
    if (watchdogRef.current) { clearTimeout(watchdogRef.current); watchdogRef.current = null; }
    if (streamRef.current) {
      try { streamRef.current.getTracks().forEach((t) => t.stop()); } catch { /* */ }
      streamRef.current = null;
    }
    if (videoRef.current) {
      try {
        videoRef.current.pause();
        videoRef.current.srcObject = null;
        videoRef.current.removeAttribute('src');
        videoRef.current.load();
      } catch { /* */ }
    }
  }, []);

  // Decode loop: grabs a frame, runs jsQR, on hit -> confirm stage
  const startDecodeLoop = useCallback(() => {
    decodedRef.current = false;
    const tick = () => {
      if (decodedRef.current) return;
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || video.readyState !== video.HAVE_ENOUGH_DATA) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }
      const w = video.videoWidth;
      const h = video.videoHeight;
      if (!w || !h) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }
      // Downscale for speed (max 600px on the long edge)
      const maxDim = 600;
      const scale = Math.min(1, maxDim / Math.max(w, h));
      const cw = Math.floor(w * scale);
      const ch = Math.floor(h * scale);
      if (canvas.width !== cw) canvas.width = cw;
      if (canvas.height !== ch) canvas.height = ch;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(video, 0, 0, cw, ch);
      try {
        const img = ctx.getImageData(0, 0, cw, ch);
        const result = jsQR(img.data, cw, ch, { inversionAttempts: 'attemptBoth' });
        if (result && result.data) {
          decodedRef.current = true;
          const parsed = parseUpi(result.data);
          setMerchant((m) => ({
            ...m,
            upi: parsed.upi || result.data.slice(0, 100),
            name: parsed.name || m.name,
          }));
          stopCamera();
          setStage('confirm');
          toast.success('QR detected!');
          return;
        }
      } catch { /* draw security errors etc. — ignore one frame */ }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [stopCamera]);

  // Snapshot live camera diagnostics — surfaces real reason for a black-frame to the user
  const snapshotDiag = useCallback(() => {
    const v = videoRef.current;
    const track = streamRef.current?.getVideoTracks?.()[0];
    setDiag({
      ready: v?.readyState ?? 0,
      vw: v?.videoWidth ?? 0,
      vh: v?.videoHeight ?? 0,
      trackMuted: track ? track.muted : null,
      trackState: track ? track.readyState : '',
    });
  }, []);

  // Open camera with native getUserMedia. iOS-safe order:
  //   1) Set video element attributes FIRST (playsinline / muted / autoplay)
  //   2) Then assign srcObject
  //   3) Wait for loadedmetadata before calling play()
  //   4) Watchdog: if videoWidth stays 0 for >4s we surface a diagnostics error
  const startCamera = useCallback(async (opts = {}) => {
    const myToken = ++startTokenRef.current;
    setScanStatus('starting');
    setScanError('');

    // Pre-flight: no MediaDevices API at all (older browsers / strict WebViews)
    const hasMediaApi = typeof navigator !== 'undefined'
      && !!navigator.mediaDevices
      && typeof navigator.mediaDevices.getUserMedia === 'function';
    if (!hasMediaApi) {
      setScanStatus(browserInfo.isInApp ? 'inapp' : 'error');
      setScanError(
        browserInfo.isInApp
          ? `${browserInfo.name} blocks camera. Open in Safari/Chrome.`
          : 'Camera not available in this browser.'
      );
      return;
    }

    // Pre-prepare the <video> element BEFORE attaching the stream (critical for iOS Safari)
    const video = videoRef.current;
    if (video) {
      try {
        video.setAttribute('playsinline', 'true');
        video.setAttribute('webkit-playsinline', 'true');
        video.setAttribute('autoplay', 'true');
        video.setAttribute('muted', 'true');
        video.muted = true;
        video.playsInline = true;
        video.autoplay = true;
        video.controls = false;
      } catch { /* */ }
    }

    // Build constraints — prefer back camera unless explicitly switched.
    // Note: parens are required around `??` before `?:` (operator precedence).
    const preferFront = (opts.useFront !== undefined ? opts.useFront : useFrontCamera);
    const facing = preferFront ? 'user' : 'environment';
    const constraints = opts.deviceId
      ? { video: { deviceId: { exact: opts.deviceId } }, audio: false }
      : { video: { facingMode: { ideal: facing } }, audio: false };

    let stream;
    try {
      // Race getUserMedia against a 12s timeout — catches the dreaded "hangs forever" bug
      stream = await Promise.race([
        navigator.mediaDevices.getUserMedia(constraints),
        new Promise((_, rej) => setTimeout(() => rej(new Error('CAMERA_TIMEOUT')), 12000)),
      ]);
    } catch (err) {
      if (myToken !== startTokenRef.current) return; // stale
      const denied = err && (err.name === 'NotAllowedError' || err.name === 'SecurityError');
      const notFound = err && (err.name === 'NotFoundError' || err.name === 'OverconstrainedError');
      const timedOut = err?.message === 'CAMERA_TIMEOUT';
      if (browserInfo.isInApp) {
        setScanStatus('inapp');
        setScanError(`${browserInfo.name} blocks camera. Tap "Open in Safari/Chrome" below.`);
      } else if (denied) {
        setScanStatus('denied');
        setScanError('Camera permission denied. Allow camera in browser settings and tap Retry.');
      } else if (notFound) {
        // Fallback: retry without facingMode constraint (some devices choke on `environment`)
        if (!opts.relaxed) {
          try {
            const relaxed = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
            stream = relaxed;
          } catch (err2) {
            setScanStatus('error');
            setScanError(`No camera matched. (${err2?.name || 'unknown'}) Tap Retry.`);
            return;
          }
        } else {
          setScanStatus('error');
          setScanError('No camera found on this device.');
          return;
        }
      } else if (timedOut) {
        setScanStatus('error');
        setScanError('Camera took too long to respond. Tap Retry, or check if another app is using the camera.');
      } else {
        setScanStatus('error');
        setScanError(`Camera error: ${err?.message || err?.name || 'unknown'}. Tap Retry.`);
      }
      if (!stream) return;
    }

    if (myToken !== startTokenRef.current) {
      // A newer start() invocation supersedes this one — release the stream
      try { stream.getTracks().forEach((t) => t.stop()); } catch { /* */ }
      return;
    }

    streamRef.current = stream;
    if (!video) {
      try { stream.getTracks().forEach((t) => t.stop()); } catch { /* */ }
      return;
    }

    // Listen for track state changes (iOS sometimes mutes the track silently)
    try {
      const track = stream.getVideoTracks()[0];
      if (track) {
        track.addEventListener?.('mute', snapshotDiag);
        track.addEventListener?.('unmute', snapshotDiag);
        track.addEventListener?.('ended', () => {
          if (myToken !== startTokenRef.current) return;
          setScanStatus('error');
          setScanError('Camera stopped unexpectedly. Tap Retry.');
          snapshotDiag();
        });
      }
    } catch { /* */ }

    // Wire metadata/playing handlers BEFORE attaching srcObject
    const onLoadedMetadata = () => {
      if (myToken !== startTokenRef.current) return;
      const playPromise = video.play();
      if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch(() => {
          // Autoplay rejected — common in some iOS in-app browsers
          setScanStatus('error');
          setScanError('Tap "Retry Camera" to grant playback permission.');
          snapshotDiag();
        });
      }
    };
    const onPlaying = () => {
      if (myToken !== startTokenRef.current) return;
      setScanStatus('running');
      snapshotDiag();
      startDecodeLoop();
    };
    video.onloadedmetadata = onLoadedMetadata;
    video.onplaying = onPlaying;

    // FINALLY attach the stream (after attrs + listeners are wired)
    try {
      video.srcObject = stream;
    } catch (err) {
      setScanStatus('error');
      setScanError(`Could not attach stream: ${err?.message || 'unknown'}`);
      return;
    }

    // Some browsers won't fire loadedmetadata if metadata is already there — kick play() once
    if (video.readyState >= 1) {
      try { onLoadedMetadata(); } catch { /* */ }
    }

    // Track the active device for switch button
    try {
      const tracks = stream.getVideoTracks();
      const settings = tracks[0]?.getSettings?.() || {};
      if (settings.deviceId) setCurrentDeviceId(settings.deviceId);
    } catch { /* */ }

    // Enumerate cameras (now that permission has been granted, labels are visible)
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const cams = devices.filter((d) => d.kind === 'videoinput');
      setCameraList(cams);
    } catch { /* */ }

    // Watchdog: if after 4.5s we still have 0 video dimensions, surface diagnostics
    if (watchdogRef.current) clearTimeout(watchdogRef.current);
    watchdogRef.current = setTimeout(() => {
      if (myToken !== startTokenRef.current) return;
      snapshotDiag();
      const v = videoRef.current;
      if (!v || v.videoWidth === 0 || v.videoHeight === 0) {
        setScanStatus('error');
        setScanError('Camera stream is blank. Tap Retry, switch camera, or enter UPI manually.');
      }
    }, 4500);
  }, [browserInfo, useFrontCamera, startDecodeLoop, snapshotDiag]);

  // Trigger camera when stage becomes 'scan'; teardown on leave
  useEffect(() => {
    if (stage !== 'scan') return;
    startCamera();
    return () => {
      startTokenRef.current++; // invalidate any pending start
      stopCamera();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  const switchCamera = async () => {
    if (cameraList.length < 2) return;
    const idx = cameraList.findIndex((c) => c.deviceId === currentDeviceId);
    const next = cameraList[(idx + 1) % cameraList.length];
    if (!next) return;
    stopCamera();
    await new Promise((r) => setTimeout(r, 100));
    startCamera({ deviceId: next.deviceId });
  };

  const retryCamera = () => {
    stopCamera();
    setScanError('');
    setScanStatus('starting');
    setTimeout(() => startCamera(), 60);
  };

  const skipScan = () => {
    stopCamera();
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
    try { window.open(url, '_blank', 'noopener,noreferrer'); } catch { /* */ }
  };

  // UPI deep-link schemes per app. Path differs per app:
  //  - upi/gpay (tez) / bhim / amazonpay use   <scheme>://upi/pay?...
  //  - phonepe / paytmmp / whatsapp use        <scheme>://pay?...
  const UPI_APPS = [
    { id: 'gpay',     label: 'Google Pay', scheme: 'tez',        path: 'upi/pay', tint: 'bg-white text-navy border-soft' },
    { id: 'phonepe',  label: 'PhonePe',    scheme: 'phonepe',    path: 'pay',     tint: 'bg-[#5f259f] text-white border-transparent' },
    { id: 'paytm',    label: 'Paytm',      scheme: 'paytmmp',    path: 'pay',     tint: 'bg-[#00baf2] text-white border-transparent' },
    { id: 'bhim',     label: 'BHIM',       scheme: 'bhim',       path: 'upi/pay', tint: 'bg-[#ff7a00] text-white border-transparent' },
    { id: 'amazon',   label: 'Amazon Pay', scheme: 'amazonpay',  path: 'upi/pay', tint: 'bg-[#232f3e] text-white border-transparent' },
    { id: 'whatsapp', label: 'WhatsApp',   scheme: 'whatsapp',   path: 'pay',     tint: 'bg-[#25d366] text-white border-transparent' },
    { id: 'other',    label: 'Other UPI',  scheme: 'upi',        path: 'pay',     tint: 'bg-navy text-white border-transparent' },
  ];

  const buildUpiLink = (scheme = 'upi', path = 'pay') => {
    const params = new URLSearchParams({
      pa: merchant.upi,
      pn: merchant.name || 'Merchant',
      am: total.toFixed(2),
      cu: 'INR',
      tn: 'BILL4PE Expense',
    });
    return `${scheme}://${path}?${params.toString()}`;
  };

  const launchUpiApp = (scheme = 'upi', path = 'pay') => {
    if (!merchant.upi) { toast.error('Merchant UPI ID required'); return; }
    if (!merchant.name?.trim()) { toast.error('Merchant Name required'); return; }
    const link = buildUpiLink(scheme, path);
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
    setPaymentInitiated(true);
    setTimeout(() => {
      toast.info('Payment ke baad neeche Transaction ID daaliye.', { duration: 5000 });
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
    const isCash = merchant.method === 'Cash';
    if (!merchant.name?.trim()) { toast.error('Merchant Name required'); return; }
    if (!isCash && !merchant.upi?.trim()) { toast.error('Merchant UPI required'); return; }
    if (!isCash && !merchant.txnId?.trim()) { toast.error('Enter Transaction ID after paying'); return; }
    setStage('submitting');
    try {
      const payload = {
        category: draft.category,
        sub_category: draft.sub_category,
        items: draft.items,
        notes: draft.notes || '',
        payment: {
          merchant_name: merchant.name,
          merchant_upi: isCash ? '' : merchant.upi,
          merchant_mobile: merchant.mobile,
          transaction_id: isCash ? (merchant.txnId?.trim() || `CASH-${Date.now()}`) : merchant.txnId,
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
                  QR scan ke liye Safari/Chrome me kholiye.
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

          {/* Camera viewport — native <video> tag for max iOS compatibility */}
          <div className="flat-card p-3 relative">
            <div
              className="rounded-xl overflow-hidden bg-black aspect-square relative"
              data-testid="qr-reader"
              style={{ minHeight: '280px' }}
            >
              <video
                ref={videoRef}
                data-testid="qr-video"
                playsInline
                muted
                autoPlay
                disablePictureInPicture
                disableRemotePlayback
                controls={false}
                className="absolute inset-0 w-full h-full object-cover"
                style={{ backgroundColor: '#000' }}
              />
              {/* hidden canvas used for jsQR frame grabs */}
              <canvas ref={canvasRef} style={{ display: 'none' }} />

              {/* QR target reticle */}
              {scanStatus === 'running' && (
                <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                  <div className="w-[70%] aspect-square border-2 border-lime/70 rounded-2xl shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" />
                </div>
              )}

              {scanStatus === 'starting' && (
                <div className="absolute inset-0 rounded-xl bg-black/85 backdrop-blur-sm flex flex-col items-center justify-center text-white text-center px-6">
                  <Loader2 className="w-8 h-8 animate-spin text-lime" />
                  <div className="mt-3 text-xs uppercase tracking-[0.25em] font-bold">Starting camera…</div>
                  <div className="mt-2 text-[11px] text-white/70 leading-snug max-w-[240px]">
                    Browser permission prompt aane par <b className="text-lime">Allow</b> kariye
                  </div>
                </div>
              )}

              {(scanStatus === 'error' || scanStatus === 'denied' || scanStatus === 'inapp') && (
                <div className="absolute inset-0 rounded-xl bg-black/90 backdrop-blur-sm flex flex-col items-center justify-center text-white text-center px-5 py-4">
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
                    {scanError || 'Allow camera access in your browser settings, then retry.'}
                  </div>
                  {/* Live diagnostics — helps debug "black screen" in production */}
                  <div
                    data-testid="camera-diag-chip"
                    className="mt-2 font-mono text-[10px] text-white/55 leading-tight"
                  >
                    ready={diag.ready} • {diag.vw}×{diag.vh}
                    {diag.trackState ? ` • ${diag.trackState}` : ''}
                    {diag.trackMuted === true ? ' • muted' : ''}
                  </div>
                  <button
                    onClick={retryCamera}
                    data-testid="retry-camera-btn"
                    className="press-down mt-4 inline-flex items-center gap-2 h-11 px-5 bg-lime text-navy rounded-full font-bold text-sm"
                  >
                    <RefreshCw className="w-4 h-4" /> Retry Camera
                  </button>
                  {scanStatus === 'inapp' && (
                    <button
                      onClick={openInExternalBrowser}
                      data-testid="overlay-open-external-btn"
                      className="press-down mt-3 inline-flex items-center gap-1.5 text-[11px] text-white/80 underline underline-offset-2"
                    >
                      <ExternalLink className="w-3 h-3" /> Open in Safari/Chrome
                    </button>
                  )}
                  <button
                    onClick={skipScan}
                    data-testid="enter-manually-btn"
                    className="mt-3 text-[11px] text-white/60 underline underline-offset-2"
                  >
                    or enter UPI manually
                  </button>
                </div>
              )}

              {/* Camera switch button (when 2+ cams) */}
              {scanStatus === 'running' && cameraList.length > 1 && (
                <button
                  onClick={switchCamera}
                  data-testid="switch-camera-btn"
                  className="absolute top-3 right-3 z-10 w-10 h-10 grid place-items-center rounded-full bg-white/15 backdrop-blur text-white hover:bg-white/25"
                  aria-label="Switch camera"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-500 justify-center">
            <QrCode className="w-4 h-4" /> Scan GPay / PhonePe / Paytm / BharatPe / BHIM QR
          </div>
          <div className="flex items-center justify-center gap-3 text-xs flex-wrap">
            <button
              type="button"
              onClick={() => { setMerchant((m) => ({ ...m, method: 'Cash' })); skipScan(); }}
              data-testid="pay-cash-skip-btn"
              className="press-down inline-flex items-center gap-2 h-10 px-4 rounded-full bg-white border border-soft text-navy font-semibold"
            >
              Pay in Cash
            </button>
            <button
              type="button"
              onClick={skipScan}
              data-testid="skip-scan-manual-btn"
              className="press-down inline-flex items-center gap-2 h-10 px-4 rounded-full bg-white border border-soft text-navy font-semibold"
            >
              Enter UPI manually
            </button>
          </div>
        </div>
      )}

      {(stage === 'confirm' || stage === 'submitting') && (
        <div className="mt-5 space-y-4">
          {/* Payment Mode Toggle */}
          <div className="flat-card p-4">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Payment Mode</div>
            <div className="mt-3 grid grid-cols-2 gap-2" data-testid="payment-mode-toggle">
              <button
                type="button"
                onClick={() => setMerchant({ ...merchant, method: 'UPI' })}
                data-testid="paymode-upi-btn"
                className={`press-down h-11 rounded-xl border text-sm font-semibold ${merchant.method !== 'Cash' ? 'bg-navy text-white border-transparent' : 'bg-white text-navy border-soft'}`}
              >
                UPI / QR
              </button>
              <button
                type="button"
                onClick={() => setMerchant({ ...merchant, method: 'Cash' })}
                data-testid="paymode-cash-btn"
                className={`press-down h-11 rounded-xl border text-sm font-semibold ${merchant.method === 'Cash' ? 'bg-navy text-white border-transparent' : 'bg-white text-navy border-soft'}`}
              >
                Cash
              </button>
            </div>
          </div>

          <div className="flat-card p-5">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Merchant</div>
            <div className="mt-3 space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Name</label>
                <Input value={merchant.name} onChange={(e) => setMerchant({ ...merchant, name: e.target.value })}
                       className="mt-1 h-11 rounded-lg border-soft" data-testid="merchant-name-input" placeholder="e.g. Suresh Tiffin Centre" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">UPI ID {merchant.method === 'Cash' && '(optional)'}</label>
                <Input value={merchant.upi} onChange={(e) => setMerchant({ ...merchant, upi: e.target.value })}
                       className="mt-1 h-11 rounded-lg border-soft font-mono" data-testid="merchant-upi-input" placeholder={merchant.method === 'Cash' ? 'Skip if no UPI' : 'merchant@upi'} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Mobile (optional)</label>
                <Input value={merchant.mobile} onChange={(e) => setMerchant({ ...merchant, mobile: e.target.value })}
                       className="mt-1 h-11 rounded-lg border-soft font-mono" data-testid="merchant-mobile-input" placeholder="+91…" />
              </div>
            </div>
          </div>

          {merchant.method !== 'Cash' && (
          <div className="flat-card p-5 space-y-3">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Pay this merchant</div>
            <p className="text-xs text-slate-500 leading-snug">
              Apne pasand ka UPI app chuniye — merchant &amp; amount pre-filled aa jayega.
            </p>

            <div className="grid grid-cols-2 gap-2 pt-1" data-testid="upi-app-picker">
              {UPI_APPS.map((app) => (
                <button
                  key={app.id}
                  type="button"
                  onClick={() => launchUpiApp(app.scheme, app.path)}
                  data-testid={`pay-${app.id}-btn`}
                  className={`press-down inline-flex items-center justify-center gap-2 h-12 rounded-xl border text-sm font-bold shadow-sm ${app.tint}`}
                >
                  <Smartphone className="w-4 h-4" /> {app.label}
                </button>
              ))}
            </div>

            <div className="pt-1 text-center text-[11px] font-bold text-navy">
              Total: ₹{total.toFixed(2)}
            </div>

            <button
              onClick={copyUpiId}
              data-testid="copy-upi-btn"
              className="press-down w-full inline-flex items-center justify-center gap-2 h-11 rounded-xl bg-white border border-soft text-navy text-sm font-semibold"
            >
              <Copy className="w-4 h-4" /> Copy UPI ID
            </button>
            <div className="text-[11px] text-slate-400 text-center">
              {geo.lat && geo.lng ? (
                <span className="inline-flex items-center gap-1"><MapPin className="w-3 h-3" /> Location captured</span>
              ) : (
                <span>Location not captured</span>
              )}
            </div>
          </div>
          )}

          <div className="flat-card p-5">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">{merchant.method === 'Cash' ? 'Confirm cash payment' : 'After paying'}</div>
            <label className="block mt-3 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">{merchant.method === 'Cash' ? 'Receipt # (optional)' : 'UTR / Transaction ID'}</label>
            <Input value={merchant.txnId} onChange={(e) => setMerchant({ ...merchant, txnId: e.target.value })}
                   className="mt-1 h-11 rounded-lg border-soft font-mono" data-testid="txn-id-input" placeholder={merchant.method === 'Cash' ? 'e.g. receipt or memo no.' : '123456789012'} />
            <p className="text-[11px] text-slate-400 mt-1">{merchant.method === 'Cash' ? 'Total cash paid: ₹' + total.toFixed(2) : 'From your UPI app receipt.'}</p>
            <Button
              data-testid="confirm-payment-btn"
              onClick={submit}
              disabled={stage === 'submitting'}
              className="w-full h-12 mt-4 bg-navy hover:bg-navy/90 text-white rounded-xl font-semibold"
            >
              {stage === 'submitting' ? (
                <span className="inline-flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Saving…</span>
              ) : (
                <span className="inline-flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> {merchant.method === 'Cash' ? 'Mark Cash Paid' : 'Confirm payment'}</span>
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
