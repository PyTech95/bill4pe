import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Html5Qrcode } from 'html5-qrcode';
import { QrCode, CheckCircle2, Smartphone, MapPin, Loader2 } from 'lucide-react';
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

export default function PayNow() {
  const nav = useNavigate();
  const { refreshUser } = useAuth();
  const [draft, setDraft] = useState(null);
  const [stage, setStage] = useState('scan'); // scan | confirm | submitting
  const [merchant, setMerchant] = useState({ name: '', upi: '', mobile: '', txnId: '', method: 'UPI' });
  const [geo, setGeo] = useState({ lat: null, lng: null });
  const scannerRef = useRef(null);
  const startedRef = useRef(false);

  useEffect(() => {
    try {
      const d = JSON.parse(sessionStorage.getItem('bill4pe_draft') || 'null');
      if (!d) { nav('/app'); return; }
      setDraft(d);
    } catch { nav('/app'); }

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (p) => setGeo({ lat: p.coords.latitude, lng: p.coords.longitude }),
        () => { /* user denied — non-blocking */ }
      );
    }
  }, [nav]);

  const total = (draft?.items || []).reduce((s, i) => s + i.quantity * i.unit_price, 0);

  useEffect(() => {
    if (stage !== 'scan' || startedRef.current) return;
    const el = document.getElementById('qr-reader');
    if (!el) return;
    startedRef.current = true;
    const q = new Html5Qrcode('qr-reader');
    scannerRef.current = q;
    q.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: { width: 240, height: 240 } },
      (decoded) => {
        const parsed = parseUpi(decoded);
        setMerchant((m) => ({
          ...m,
          upi: parsed.upi || decoded.slice(0, 100),
          name: parsed.name || m.name,
        }));
        q.stop().catch(() => {}).then(() => setStage('confirm'));
      },
      () => { /* ignore scan errors */ }
    ).catch((err) => {
      toast.error('Camera unavailable. Enter merchant details manually.');
      setStage('confirm');
    });
    return () => {
      try { q.stop().catch(() => {}); } catch { /* ignore */ }
      startedRef.current = false;
    };
  }, [stage]);

  const skipScan = async () => {
    try { await scannerRef.current?.stop(); } catch { /* ignore */ }
    setStage('confirm');
  };

  const launchUpiApp = () => {
    if (!merchant.upi) { toast.error('Merchant UPI ID required'); return; }
    const params = new URLSearchParams({
      pa: merchant.upi,
      pn: merchant.name || 'Merchant',
      am: total.toFixed(2),
      cu: 'INR',
      tn: 'BILL4PE Expense',
    });
    const link = `upi://pay?${params.toString()}`;
    window.location.href = link;
    setTimeout(() => {
      toast.info('Returning from UPI app? Enter the Transaction ID below.');
    }, 1500);
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
        payment: {
          merchant_name: merchant.name,
          merchant_upi: merchant.upi,
          merchant_mobile: merchant.mobile,
          transaction_id: merchant.txnId,
          amount: total,
          latitude: geo.lat,
          longitude: geo.lng,
          payment_method: merchant.method,
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
          <div className="flat-card p-3">
            <div id="qr-reader" className="rounded-xl overflow-hidden bg-black aspect-square" />
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500 justify-center">
            <QrCode className="w-4 h-4" /> Scan GPay / PhonePe / Paytm / BharatPe / BHIM QR
          </div>
          <button
            onClick={skipScan}
            data-testid="skip-scan-btn"
            className="w-full text-sm text-slate-500 underline"
          >
            Can't scan? Enter UPI ID manually
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
            onClick={launchUpiApp}
            data-testid="launch-upi-btn"
            className="press-down w-full bg-navy text-white rounded-2xl p-4 flex items-center justify-between hover:bg-[#152042]"
          >
            <span className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-lime text-navy grid place-items-center">
                <Smartphone className="w-5 h-5" />
              </div>
              <span>
                <div className="font-display font-bold">Open UPI App</div>
                <div className="text-xs text-white/60">Pay ₹{total.toFixed(2)} via GPay/PhonePe/Paytm</div>
              </span>
            </span>
            <CheckCircle2 className="w-5 h-5 text-lime" />
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
            className="press-down w-full h-12 bg-lime text-navy hover:bg-[#BCE300] rounded-full font-semibold"
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
