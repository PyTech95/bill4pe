import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Plane, MapPin, ArrowRight, Loader2, RefreshCw, Mic, Square,
  StickyNote, Navigation, Crosshair,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { catByKey } from '@/lib/categories';
import api from '@/lib/api';

// Map sub-category → merchant nature of business (printed on bill)
const TRAVEL_NATURE = {
  'Auto Booking': 'Auto Driver',
  'E-Rickshaw Booking': 'E-Rickshaw Driver',
  'Bike Booking': 'Bike Taxi Driver',
  'Cab Booking': 'Cab Driver',
  'Bus Booking': 'Bus Operator',
  'Taxi Booking': 'Taxi Driver',
  'Self Booking': 'Self / Fuel & Toll',
  'Flight': 'Airline',
  'Train': 'Indian Railways',
  'Toll': 'Toll Plaza',
};

// Reverse-geocode lat/lng → human address using OpenStreetMap Nominatim (free, no key).
const reverseGeocode = async (lat, lng) => {
  try {
    const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&zoom=14&addressdetails=1`;
    const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
    if (!res.ok) return '';
    const data = await res.json();
    const a = data?.address || {};
    // Prefer suburb / neighbourhood / village / town / city — shortest meaningful name
    const short = a.suburb || a.neighbourhood || a.village || a.town || a.city_district || a.city || a.county || '';
    if (short) return short;
    const dn = data?.display_name || '';
    return dn.split(',').slice(0, 2).join(',').trim();
  } catch {
    return '';
  }
};

export default function TravelSubCategory() {
  const cat = 'travel';
  const nav = useNavigate();
  const c = catByKey(cat);

  const [serviceType, setServiceType] = useState(c?.sub?.[0] || 'Auto Booking');
  const [fromText, setFromText] = useState('');
  const [toText, setToText] = useState('');
  const [amount, setAmount] = useState('');
  const [notes, setNotes] = useState('');

  // Pickup geolocation (captured on mount)
  const [pickup, setPickup] = useState({ lat: null, lng: null, status: 'idle' });

  // Notes voice recording (reused from food page)
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recorderRef = useRef(null);
  const recChunksRef = useRef([]);
  const recStreamRef = useRef(null);
  const fromAutoFilledRef = useRef(false);

  const capturePickup = () => {
    if (!navigator.geolocation) { setPickup({ lat: null, lng: null, status: 'unsupported' }); return; }
    setPickup((g) => ({ ...g, status: 'loading' }));
    navigator.geolocation.getCurrentPosition(
      async (p) => {
        const lat = p.coords.latitude, lng = p.coords.longitude;
        setPickup({ lat, lng, status: 'ok' });
        // Auto-fill "From" if user hasn't typed anything
        if (!fromAutoFilledRef.current) {
          const place = await reverseGeocode(lat, lng);
          if (place) {
            setFromText((cur) => cur ? cur : place);
            fromAutoFilledRef.current = true;
          }
        }
      },
      (err) => {
        const denied = err && err.code === 1;
        setPickup({ lat: null, lng: null, status: denied ? 'denied' : 'error' });
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  };

  useEffect(() => { capturePickup(); /* eslint-disable-next-line */ }, []);

  // Capture dropping point GPS just before submit; navigates with full draft.
  const proceed = () => {
    const amt = Number(amount);
    if (!amt || amt <= 0) { toast.error('Enter the amount you will pay'); return; }
    if (!toText.trim()) { toast.error('Enter the "To" destination'); return; }
    const finish = (drop) => {
      const tripLabel = `${serviceType}: ${fromText.trim() || '—'} → ${toText.trim()}`;
      sessionStorage.setItem('bill4pe_draft', JSON.stringify({
        category: cat,
        sub_category: serviceType,
        items: [{ name: tripLabel, quantity: 1, unit_price: amt }],
        notes: notes?.trim() || '',
        prefill_geo: pickup.status === 'ok' ? { lat: pickup.lat, lng: pickup.lng } : null,
        trip_meta: {
          from_text: fromText.trim(),
          to_text: toText.trim(),
          pickup_lat: pickup.lat,
          pickup_lng: pickup.lng,
          drop_lat: drop?.lat ?? null,
          drop_lng: drop?.lng ?? null,
          nature_of_business: TRAVEL_NATURE[serviceType] || 'Travel',
        },
      }));
      nav('/app/pay');
    };
    if (!navigator.geolocation) { finish(null); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => finish({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => finish(null),
      { enableHighAccuracy: true, timeout: 7000, maximumAge: 30000 }
    );
  };

  // -------- Notes voice recording --------
  const startNotesRec = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      toast.error('Voice recording not supported');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recStreamRef.current = stream;
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '');
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      recorderRef.current = rec;
      recChunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data?.size) recChunksRef.current.push(e.data); };
      rec.onstop = onNotesRecStop;
      rec.start();
      setRecording(true);
    } catch {
      toast.error('Microphone permission denied');
    }
  };
  const stopNotesRec = () => { try { recorderRef.current?.stop(); } catch { /* */ } };
  const onNotesRecStop = async () => {
    setRecording(false);
    try { recStreamRef.current?.getTracks().forEach((t) => t.stop()); } catch { /* */ }
    recStreamRef.current = null;
    const chunks = recChunksRef.current;
    recChunksRef.current = [];
    if (!chunks.length) return;
    setTranscribing(true);
    try {
      const blob = new Blob(chunks, { type: chunks[0]?.type || 'audio/webm' });
      const fd = new FormData();
      fd.append('file', blob, 'note.webm');
      const { data } = await api.post('/voice/expense', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const txt = (data?.transcript || '').trim();
      if (txt) { setNotes((n) => (n ? `${n} ${txt}` : txt)); toast.success('Note transcribed'); }
      else toast.warning('Could not hear anything');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Transcription failed');
    } finally { setTranscribing(false); }
  };

  const tripLabel = useMemo(
    () => `${serviceType}: ${fromText.trim() || '—'} → ${toText.trim() || '—'}`,
    [serviceType, fromText, toText]
  );

  if (!c) return <div>Unknown category.</div>;
  const totalNum = Number(amount) || 0;

  return (
    <div className="pb-32 space-y-5" data-testid="travel-subcategory">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-11 h-11 rounded-2xl bg-navy text-white grid place-items-center">
          <Plane className="w-5 h-5" />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-slate-400 font-bold">Category</div>
          <h1 className="font-display text-xl font-bold text-navy leading-tight">{c.label}</h1>
        </div>
      </div>

      {/* Service Picker */}
      <div>
        <label className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-bold">
          Pick the service
        </label>
        <Select value={serviceType} onValueChange={setServiceType}>
          <SelectTrigger
            className="mt-2 h-12 rounded-xl border-soft bg-white"
            data-testid="travel-service-trigger"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {c.sub.map((s) => (
              <SelectItem key={s} value={s} data-testid={`travel-service-${s}`}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="mt-1.5 text-[10px] text-slate-400">
          Nature of business on bill: <span className="font-semibold text-navy">{TRAVEL_NATURE[serviceType] || 'Travel'}</span>
        </div>
      </div>

      {/* Destination Block */}
      <div className="flat-card p-0 overflow-hidden">
        <div className="px-4 py-3 bg-navy text-white flex items-center gap-2">
          <Navigation className="w-4 h-4 text-lime" />
          <div className="text-[11px] uppercase tracking-[0.25em] text-lime font-bold">Destination</div>
        </div>
        <div className="p-4 space-y-3">
          {/* From */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">From</label>
            <div className="relative mt-1">
              <Crosshair className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-emerald-500" />
              <Input
                placeholder={pickup.status === 'loading' ? 'Detecting current location…' : 'e.g. ICD Tugalakabad'}
                value={fromText}
                onChange={(e) => { fromAutoFilledRef.current = true; setFromText(e.target.value); }}
                className="pl-9 h-11 rounded-lg border-soft"
                data-testid="trip-from-input"
              />
            </div>
            <div className="mt-1 text-[10px] text-slate-400 flex items-center gap-1.5">
              <MapPin className="w-2.5 h-2.5" />
              {pickup.status === 'ok' && pickup.lat ? (
                <span className="font-mono">
                  {pickup.lat.toFixed(5)}, {pickup.lng.toFixed(5)}
                  <span className="ml-1 text-emerald-600 font-semibold">· auto-captured</span>
                </span>
              ) : pickup.status === 'loading' ? (
                <span className="inline-flex items-center gap-1"><Loader2 className="w-2.5 h-2.5 animate-spin" /> Getting GPS</span>
              ) : pickup.status === 'denied' ? (
                <span className="text-red-500">GPS permission denied</span>
              ) : (
                <span>GPS not captured</span>
              )}
            </div>
          </div>

          {/* To */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">To</label>
            <div className="relative mt-1">
              <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-brand" />
              <Input
                placeholder="e.g. DLF Cyber City"
                value={toText}
                onChange={(e) => setToText(e.target.value)}
                className="pl-9 h-11 rounded-lg border-soft"
                data-testid="trip-to-input"
              />
            </div>
          </div>

          {/* Amount */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Amount (₹)</label>
            <Input
              type="number" min="0" step="1"
              placeholder="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="mt-1 h-12 rounded-lg border-soft font-mono text-lg font-bold text-navy"
              data-testid="trip-amount-input"
            />
            <div className="mt-1 text-[10px] text-slate-400">
              Enter the amount you'll pay via UPI / QR
            </div>
          </div>
        </div>
      </div>

      {/* Notes */}
      <div className="flat-card p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <StickyNote className="w-4 h-4 text-navy" />
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-bold">
              Notes (optional)
            </div>
          </div>
          {!recording && !transcribing && (
            <button type="button" onClick={startNotesRec} data-testid="notes-mic-btn"
              className="press-down inline-flex items-center gap-1.5 h-9 px-3 rounded-full bg-navy text-lime text-xs font-bold hover:bg-[#152042]">
              <Mic className="w-3.5 h-3.5" /> Speak
            </button>
          )}
          {recording && (
            <button type="button" onClick={stopNotesRec} data-testid="notes-stop-btn"
              className="press-down inline-flex items-center gap-1.5 h-9 px-3 rounded-full bg-red-500 text-white text-xs font-bold animate-pulse">
              <Square className="w-3 h-3 fill-current" /> Stop
            </button>
          )}
          {transcribing && (
            <div className="inline-flex items-center gap-1.5 h-9 px-3 rounded-full bg-brand/10 text-brand text-xs font-bold">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Transcribing
            </div>
          )}
        </div>
        <Textarea
          placeholder='e.g. "Office cab to client meeting at Cyber Hub" or tap Speak'
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="mt-3 rounded-lg border-soft min-h-[64px] text-sm"
          data-testid="notes-textarea"
          maxLength={500}
        />
      </div>

      {/* Trip preview chip */}
      <div className="px-1 text-xs text-slate-500">
        <span className="font-semibold text-navy">Trip:</span> {tripLabel}
      </div>

      {/* Sticky pay-now bar */}
      <div className="fixed bottom-14 left-0 right-0 z-20 backdrop-blur-xl bg-white/95 border-t border-soft">
        <div className="max-w-screen-sm mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-bold">Total</div>
            <div className="font-mono text-xl font-bold text-navy" data-testid="bottom-bar-total">
              ₹ {totalNum.toFixed(2)}
            </div>
          </div>
          <Button
            onClick={proceed} disabled={totalNum <= 0}
            className="press-down h-12 px-6 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
            data-testid="proceed-to-pay-btn"
          >
            Pay Now <ArrowRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      </div>

      {/* Tiny refresh GPS button (corner) */}
      {(pickup.status === 'denied' || pickup.status === 'error') && (
        <div className="text-center">
          <button
            onClick={capturePickup}
            data-testid="enable-gps-btn"
            className="press-down inline-flex items-center gap-1.5 h-9 px-3 rounded-full bg-brand text-white text-xs font-semibold hover:bg-[#1858CC]"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Retry GPS
          </button>
        </div>
      )}
    </div>
  );
}
