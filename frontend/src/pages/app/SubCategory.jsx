import React, { useEffect, useMemo, useState, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  QrCode, MapPin, Plus, Trash2, ArrowRight, Camera, ScanLine, Loader2, Building2,
  Phone, ChevronDown, Sparkles, X, RefreshCw,
} from 'lucide-react';
import { Html5Qrcode } from 'html5-qrcode';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from '@/components/ui/sheet';
import { toast } from 'sonner';
import { catByKey } from '@/lib/categories';
import api from '@/lib/api';

const emptyItem = () => ({ name: '', quantity: 1, unit_price: 0 });

const parseUpi = (data) => {
  try {
    if (!data?.toLowerCase().startsWith('upi://')) return { upi: '', name: '' };
    const q = data.split('?')[1] || '';
    const params = Object.fromEntries(new URLSearchParams(q));
    return { upi: params.pa || '', name: decodeURIComponent(params.pn || '') };
  } catch { return { upi: '', name: '' }; }
};

export default function SubCategory() {
  const { cat } = useParams();
  const nav = useNavigate();
  const c = catByKey(cat);
  const Icon = c?.icon || Building2;

  const [serviceType, setServiceType] = useState(c?.sub?.[0] || '');
  const [merchant, setMerchant] = useState({ name: '', upi: '', mobile: '' });
  const [items, setItems] = useState([emptyItem()]);
  const [geo, setGeo] = useState({ lat: null, lng: null, status: 'idle' });
  const [scanOpen, setScanOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiScanning, setAiScanning] = useState(false);
  const [preview, setPreview] = useState(null);

  const fileRef = useRef(null);
  const scannerRef = useRef(null);

  // Capture geolocation (callable + auto on mount)
  const captureLocation = () => {
    if (!navigator.geolocation) {
      setGeo({ lat: null, lng: null, status: 'unsupported' });
      return;
    }
    setGeo((g) => ({ ...g, status: 'loading' }));
    navigator.geolocation.getCurrentPosition(
      (p) => setGeo({ lat: p.coords.latitude, lng: p.coords.longitude, status: 'ok' }),
      (err) => {
        const denied = err && err.code === 1;
        setGeo({ lat: null, lng: null, status: denied ? 'denied' : 'error' });
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 }
    );
  };

  // Auto-capture location on first render
  useEffect(() => {
    captureLocation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // QR scanner lifecycle
  useEffect(() => {
    if (!scanOpen) return;
    const id = setTimeout(() => {
      const q = new Html5Qrcode('merchant-qr-reader');
      scannerRef.current = q;
      q.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 220, height: 220 } },
        (decoded) => {
          const parsed = parseUpi(decoded);
          setMerchant((m) => ({
            ...m,
            upi: parsed.upi || decoded.slice(0, 100),
            name: parsed.name || m.name,
          }));
          q.stop().catch(() => {}).then(() => setScanOpen(false));
          toast.success('Merchant info captured from QR');
        },
        () => {}
      ).catch(() => {
        toast.error('Camera unavailable');
        setScanOpen(false);
      });
    }, 200);
    return () => {
      clearTimeout(id);
      try { scannerRef.current?.stop().catch(() => {}); } catch { /* ignore */ }
    };
  }, [scanOpen]);

  // Items helpers
  const updateItem = (idx, patch) =>
    setItems((arr) => arr.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  const removeItem = (idx) =>
    setItems((arr) => arr.length === 1 ? [emptyItem()] : arr.filter((_, i) => i !== idx));
  const addItem = () => setItems((arr) => [...arr, emptyItem()]);

  const total = useMemo(
    () => items.reduce((s, i) => s + Number(i.quantity || 0) * Number(i.unit_price || 0), 0),
    [items]
  );

  // AI scan
  const onAiFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    setAiScanning(true);
    setAiOpen(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post(`/ai/detect-items?category=${encodeURIComponent(cat)}`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const detected = data?.items || [];
      if (!detected.length) {
        toast.warning('Could not detect items — please enter manually');
      } else {
        setItems(detected);
        toast.success(`${detected.length} items detected`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'AI detection failed');
    } finally {
      setAiScanning(false);
      setTimeout(() => setAiOpen(false), 700);
    }
  };

  const proceed = () => {
    const cleaned = items
      .filter((i) => i.name?.trim() && Number(i.quantity) > 0)
      .map((i) => ({
        name: i.name.trim(),
        quantity: Number(i.quantity),
        unit_price: Number(i.unit_price) || 0,
      }));
    if (!cleaned.length) { toast.error('Add at least one item'); return; }
    if (total <= 0) { toast.error('Total must be > 0'); return; }
    if (!merchant.name?.trim()) { toast.error('Enter merchant name'); return; }

    sessionStorage.setItem('bill4pe_draft', JSON.stringify({
      category: cat,
      sub_category: serviceType,
      items: cleaned,
      prefill_merchant: {
        merchant_name: merchant.name.trim(),
        merchant_upi: merchant.upi.trim(),
        merchant_mobile: merchant.mobile.trim(),
      },
      prefill_geo: geo.status === 'ok' ? { lat: geo.lat, lng: geo.lng } : null,
    }));
    nav('/app/pay');
  };

  if (!c) return <div>Unknown category.</div>;

  return (
    <div className="pb-32 space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-11 h-11 rounded-2xl bg-navy text-brand grid place-items-center">
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-slate-400 font-bold">Category</div>
          <h1 className="font-display text-xl font-bold text-navy leading-tight">{c.label}</h1>
        </div>
      </div>

      {/* Service Type Dropdown */}
      <div>
        <label className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-bold">
          Pick the service
        </label>
        <Select value={serviceType} onValueChange={setServiceType}>
          <SelectTrigger className="mt-2 h-12 rounded-xl border-soft bg-white" data-testid="service-type-trigger">
            <SelectValue placeholder={`${c.label} type`} />
          </SelectTrigger>
          <SelectContent>
            {c.sub.map((s) => (
              <SelectItem key={s} value={s} data-testid={`service-${s}`}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Merchant Card */}
      <div className="flat-card p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-bold">Merchant</div>
            <div className="text-xs text-slate-500 mt-0.5">Scan QR or enter manually</div>
          </div>
          <button
            onClick={() => setScanOpen(true)}
            data-testid="scan-merchant-qr-btn"
            className="press-down inline-flex items-center gap-1.5 h-9 px-3 rounded-full bg-brand text-white text-xs font-semibold hover:bg-[#1858CC]"
          >
            <QrCode className="w-3.5 h-3.5" /> Scan QR
          </button>
        </div>

        <div className="mt-4 space-y-3">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Name of merchant</label>
            <Input
              placeholder="e.g. Suresh Kumar"
              value={merchant.name}
              onChange={(e) => setMerchant({ ...merchant, name: e.target.value })}
              className="mt-1 h-11 rounded-lg border-soft"
              data-testid="merchant-name-input"
            />
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Mobile</label>
              <div className="relative mt-1">
                <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <Input
                  placeholder="98765 43210"
                  value={merchant.mobile} type="tel" maxLength={10}
                  onChange={(e) => setMerchant({ ...merchant, mobile: e.target.value.replace(/\D/g, '').slice(0, 10) })}
                  className="pl-9 h-11 rounded-lg border-soft font-mono"
                  data-testid="merchant-mobile-input"
                />
              </div>
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">UPI ID</label>
              <Input
                placeholder="merchant@upi"
                value={merchant.upi}
                onChange={(e) => setMerchant({ ...merchant, upi: e.target.value })}
                className="mt-1 h-11 rounded-lg border-soft font-mono text-xs"
                data-testid="merchant-upi-input"
              />
            </div>
          </div>
          <div className="text-[10px] text-slate-400 flex items-center gap-1.5">
            <Building2 className="w-3 h-3" />
            Nature of business: <span className="font-semibold text-navy">{c.label} / {serviceType || '—'}</span>
          </div>
        </div>
      </div>

      {/* AI Photo Capture — Hero CTA */}
      <motion.button
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        whileHover={{ y: -2 }}
        onClick={() => fileRef.current?.click()}
        data-testid="ai-photo-capture-btn"
        className="press-down relative w-full overflow-hidden rounded-3xl bg-navy text-white p-5 text-left group"
      >
        <div
          className="absolute inset-0 opacity-60 pointer-events-none"
          style={{
            background:
              'radial-gradient(circle at 85% 25%, rgba(31,111,235,0.40), transparent 50%),' +
              'radial-gradient(circle at 10% 90%, rgba(212,255,0,0.10), transparent 50%)',
          }}
        />
        <Camera className="absolute -right-4 -bottom-4 w-36 h-36 text-white/[0.06]" strokeWidth={1} />

        <div className="relative">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-[0.25em] bg-lime text-navy">
            <Sparkles className="w-3 h-3" /> AI Magic
          </div>

          <div className="mt-4 flex items-start gap-4">
            <div className="w-14 h-14 rounded-2xl bg-lime text-navy grid place-items-center shrink-0 shadow-lg shadow-lime/20 pulse-brand">
              <Camera className="w-7 h-7" strokeWidth={1.8} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-display text-xl font-bold leading-tight">
                Snap your {(serviceType || c.label).toLowerCase()} photo
              </div>
              <div className="text-xs text-white/60 mt-1.5 leading-relaxed">
                AI detects <span className="text-lime font-semibold">Dal, Roti, Sabji, Rice</span> & estimates
                quantities + prices — bill auto-fills in seconds.
              </div>
            </div>
          </div>

          <div className="mt-4 flex items-center gap-2">
            <div className="flex-1 inline-flex items-center justify-center gap-2 h-11 bg-brand hover:bg-[#1858CC] rounded-full text-white font-semibold text-sm transition-colors">
              <Camera className="w-4 h-4" /> Capture {(serviceType || c.label)} photo
            </div>
          </div>

          <div className="mt-3 text-[10px] text-white/40 text-center">
            or fill items manually below ↓
          </div>
        </div>
      </motion.button>

      {/* Items table */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-bold">Items (manual)</label>
          <button
            onClick={() => fileRef.current?.click()}
            data-testid="ai-scan-btn"
            className="press-down inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider bg-lime text-navy px-2 py-1 rounded-full"
          >
            <Sparkles className="w-3 h-3" /> Re-scan
          </button>
        </div>

        <div className="flat-card overflow-hidden">
          {/* table header */}
          <div className="grid grid-cols-12 gap-2 px-3 py-2 bg-[#F4F5F7] border-b border-soft text-[10px] uppercase tracking-wider font-bold text-slate-500">
            <div className="col-span-6">Particular</div>
            <div className="col-span-2 text-center">Qty</div>
            <div className="col-span-3 text-right">Amount (₹)</div>
            <div className="col-span-1"></div>
          </div>

          {items.map((it, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 px-2 py-2 border-b border-soft last:border-0" data-testid={`item-row-${idx}`}>
              <div className="col-span-6">
                <Input
                  placeholder="e.g. Roti"
                  value={it.name}
                  onChange={(e) => updateItem(idx, { name: e.target.value })}
                  className="h-9 rounded-md border-soft text-sm"
                  data-testid={`item-name-input-${idx}`}
                />
              </div>
              <div className="col-span-2">
                <Input
                  type="number" min="0" step="1"
                  value={it.quantity}
                  onChange={(e) => updateItem(idx, { quantity: e.target.value })}
                  className="h-9 rounded-md border-soft text-sm font-mono text-center px-1"
                  data-testid={`item-qty-${idx}`}
                />
              </div>
              <div className="col-span-3">
                <Input
                  type="number" min="0" step="0.01"
                  value={it.unit_price}
                  onChange={(e) => updateItem(idx, { unit_price: e.target.value })}
                  className="h-9 rounded-md border-soft text-sm font-mono text-right"
                  data-testid={`item-price-${idx}`}
                />
              </div>
              <div className="col-span-1 flex items-center justify-center">
                <button
                  onClick={() => removeItem(idx)}
                  className="press-down p-1.5 text-slate-300 hover:text-red-500"
                  data-testid={`item-remove-${idx}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}

          {/* add row */}
          <button
            onClick={addItem}
            data-testid="add-item-btn"
            className="press-down w-full py-2.5 text-xs font-semibold text-navy hover:bg-slate-50 inline-flex items-center justify-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" /> Add item
          </button>

          {/* total */}
          <div className="bg-navy text-white px-3 py-2.5 flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider font-bold text-brand">Total</span>
            <span className="font-mono font-bold text-lg" data-testid="bill-total">₹ {total.toFixed(2)}</span>
          </div>
        </div>

        <input
          ref={fileRef} type="file" accept="image/*" capture="environment"
          className="hidden" onChange={onAiFile}
          data-testid="ai-file-input"
        />
      </div>

      {/* Location */}
      <div className={`flat-card p-4 flex items-center gap-3 ${geo.status === 'denied' ? 'border-red-200 bg-red-50' : geo.status === 'ok' ? 'border-emerald-200' : ''}`}>
        <div className={`w-9 h-9 rounded-lg grid place-items-center shrink-0 ${
          geo.status === 'ok' ? 'bg-emerald-500/10 text-emerald-600' :
          geo.status === 'denied' ? 'bg-red-500/10 text-red-500' :
          'bg-[#0A1128]/5 text-navy'
        }`}>
          <MapPin className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">
            GPS Location
          </div>
          {geo.status === 'ok' && geo.lat ? (
            <div className="font-mono text-xs text-navy mt-0.5">
              {geo.lat.toFixed(5)}, {geo.lng.toFixed(5)}{' '}
              <span className="text-emerald-600 font-semibold">· captured</span>
            </div>
          ) : geo.status === 'loading' ? (
            <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" /> Getting your location...
            </div>
          ) : geo.status === 'denied' ? (
            <div className="text-xs text-red-600 mt-0.5">
              Permission denied. Enable in browser settings.
            </div>
          ) : geo.status === 'unsupported' ? (
            <div className="text-xs text-slate-500 mt-0.5">
              Your browser doesn't support location.
            </div>
          ) : (
            <div className="text-xs text-slate-500 mt-0.5">
              Tap to attach location to bill
            </div>
          )}
        </div>
        {(geo.status === 'denied' || geo.status === 'error' || geo.status === 'idle') && (
          <button
            onClick={captureLocation}
            data-testid="enable-gps-btn"
            className="press-down h-9 px-3 rounded-full bg-brand text-white text-xs font-semibold hover:bg-[#1858CC]"
          >
            Enable GPS
          </button>
        )}
        {geo.status === 'ok' && (
          <button
            onClick={captureLocation}
            data-testid="refresh-gps-btn"
            className="press-down h-9 w-9 grid place-items-center rounded-full border border-soft hover:border-navy"
            title="Refresh location"
          >
            <RefreshCw className="w-3.5 h-3.5 text-slate-500" />
          </button>
        )}
      </div>

      {/* Sticky pay-now bar */}
      <div className="fixed bottom-14 left-0 right-0 z-20 backdrop-blur-xl bg-white/95 border-t border-soft">
        <div className="max-w-screen-sm mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-bold">Total</div>
            <div className="font-mono text-xl font-bold text-navy" data-testid="bottom-bar-total">₹ {total.toFixed(2)}</div>
          </div>
          <Button
            onClick={proceed} disabled={total <= 0}
            className="press-down h-12 px-6 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
            data-testid="proceed-to-pay-btn"
          >
            Pay Now <ArrowRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      </div>

      {/* QR scan sheet */}
      <Sheet open={scanOpen} onOpenChange={setScanOpen}>
        <SheetContent side="bottom" className="rounded-t-3xl border-0 px-5 pb-8 pt-7">
          <SheetHeader className="text-left">
            <SheetTitle className="font-display text-2xl text-navy">Scan merchant QR</SheetTitle>
          </SheetHeader>
          <div className="mt-4 flat-card p-2">
            <div id="merchant-qr-reader" className="rounded-xl overflow-hidden bg-black aspect-square" />
          </div>
          <div className="mt-3 text-xs text-slate-500 text-center flex items-center justify-center gap-1.5">
            <ScanLine className="w-3 h-3" /> Point at GPay / PhonePe / Paytm / BharatPe / BHIM QR
          </div>
        </SheetContent>
      </Sheet>

      {/* AI scanning overlay */}
      {aiOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm grid place-items-center px-6">
          <div className="relative w-full max-w-sm aspect-square rounded-3xl overflow-hidden bg-black">
            {preview && <img src={preview} alt="scan" className="absolute inset-0 w-full h-full object-cover opacity-70" />}
            {aiScanning && <div className="scan-laser" />}
            <button
              onClick={() => { setAiOpen(false); setAiScanning(false); }}
              className="absolute top-3 right-3 w-9 h-9 grid place-items-center bg-white/10 backdrop-blur rounded-full text-white"
              data-testid="close-ai-scan"
            >
              <X className="w-4 h-4" />
            </button>
            <div className="absolute inset-x-0 bottom-0 p-4 bg-gradient-to-t from-black/80 to-transparent text-white">
              <div className="flex items-center gap-2 text-brand text-xs uppercase tracking-wider font-bold">
                {aiScanning && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {aiScanning ? 'AI detecting items...' : 'Done'}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
