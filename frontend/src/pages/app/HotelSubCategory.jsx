import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BedDouble, MapPin, ArrowRight, Loader2, RefreshCw, Mic, Square,
  StickyNote, CalendarDays, Hotel as HotelIcon, Moon,
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

const HOTEL_NATURE = {
  'Standard Room': 'Hotel & Lodging',
  'Deluxe Room': 'Hotel & Lodging',
  'Suite': 'Hotel & Lodging',
  'Family Room': 'Hotel & Lodging',
  'Dormitory': 'Hostel / Dormitory',
  'Other': 'Hospitality',
};

const todayStr = () => {
  const d = new Date();
  const tz = d.getTimezoneOffset() * 60000;
  return new Date(d - tz).toISOString().slice(0, 10);
};

const addDays = (yyyyMmDd, n) => {
  const d = new Date(yyyyMmDd + 'T00:00:00');
  d.setDate(d.getDate() + n);
  const tz = d.getTimezoneOffset() * 60000;
  return new Date(d - tz).toISOString().slice(0, 10);
};

const nightsBetween = (a, b) => {
  if (!a || !b) return 0;
  const da = new Date(a + 'T00:00:00');
  const db = new Date(b + 'T00:00:00');
  const ms = db - da;
  return Math.max(0, Math.round(ms / (1000 * 60 * 60 * 24)));
};

export default function HotelSubCategory() {
  const cat = 'hotel';
  const nav = useNavigate();
  const c = catByKey(cat);

  const [roomType, setRoomType] = useState(c?.sub?.[0] || 'Standard Room');
  const [hotelName, setHotelName] = useState('');
  const [checkIn, setCheckIn] = useState(todayStr());
  const [checkOut, setCheckOut] = useState(addDays(todayStr(), 1));
  const [perNight, setPerNight] = useState('');
  const [notes, setNotes] = useState('');

  const [geo, setGeo] = useState({ lat: null, lng: null, status: 'idle' });

  // Notes voice recording
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recorderRef = useRef(null);
  const recChunksRef = useRef([]);
  const recStreamRef = useRef(null);

  const captureLocation = () => {
    if (!navigator.geolocation) { setGeo({ lat: null, lng: null, status: 'unsupported' }); return; }
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

  useEffect(() => { captureLocation(); /* eslint-disable-next-line */ }, []);

  // Keep check-out at least 1 day after check-in
  useEffect(() => {
    if (checkOut && checkOut <= checkIn) {
      setCheckOut(addDays(checkIn, 1));
    }
    // eslint-disable-next-line
  }, [checkIn]);

  const nights = useMemo(() => nightsBetween(checkIn, checkOut), [checkIn, checkOut]);
  const rate = Number(perNight) || 0;
  const total = nights * rate;

  const proceed = () => {
    if (!hotelName.trim()) { toast.error('Enter the hotel name'); return; }
    if (nights <= 0) { toast.error('Check-out must be after check-in'); return; }
    if (rate <= 0) { toast.error('Enter the per-night rate'); return; }

    const itemLabel = `${roomType} · ${nights} night${nights > 1 ? 's' : ''} @ ${hotelName.trim()}`;
    sessionStorage.setItem('bill4pe_draft', JSON.stringify({
      category: cat,
      sub_category: roomType,
      items: [{ name: itemLabel, quantity: nights, unit_price: rate }],
      notes: notes?.trim() || '',
      prefill_geo: geo.status === 'ok' ? { lat: geo.lat, lng: geo.lng } : null,
      stay_meta: {
        hotel_name: hotelName.trim(),
        room_type: roomType,
        check_in: checkIn,
        check_out: checkOut,
        nights,
        per_night_rate: rate,
        nature_of_business: HOTEL_NATURE[roomType] || 'Hospitality',
      },
    }));
    nav('/app/pay');
  };

  // -------- Notes voice recording --------
  const startNotesRec = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      toast.error('Voice recording not supported'); return;
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
    } catch { toast.error('Microphone permission denied'); }
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
    } catch (err) { toast.error(err?.response?.data?.detail || 'Transcription failed'); }
    finally { setTranscribing(false); }
  };

  if (!c) return <div>Unknown category.</div>;

  return (
    <div className="pb-32 space-y-5" data-testid="hotel-subcategory">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-11 h-11 rounded-2xl bg-navy text-white grid place-items-center">
          <BedDouble className="w-5 h-5" />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-slate-400 font-bold">Category</div>
          <h1 className="font-display text-xl font-bold text-navy leading-tight">{c.label}</h1>
        </div>
      </div>

      {/* Room Type Picker */}
      <div>
        <label className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-bold">
          Room Type
        </label>
        <Select value={roomType} onValueChange={setRoomType}>
          <SelectTrigger className="mt-2 h-12 rounded-xl border-soft bg-white" data-testid="hotel-room-trigger">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {c.sub.map((s) => (
              <SelectItem key={s} value={s} data-testid={`hotel-room-${s}`}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="mt-1.5 text-[10px] text-slate-400">
          Nature of business on bill: <span className="font-semibold text-navy">{HOTEL_NATURE[roomType] || 'Hospitality'}</span>
        </div>
      </div>

      {/* Stay block */}
      <div className="flat-card p-0 overflow-hidden">
        <div className="px-4 py-3 bg-navy text-white flex items-center gap-2">
          <CalendarDays className="w-4 h-4 text-lime" />
          <div className="text-[11px] uppercase tracking-[0.25em] text-lime font-bold">Your Stay</div>
        </div>
        <div className="p-4 space-y-3">
          {/* Hotel name */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Hotel name</label>
            <div className="relative mt-1">
              <HotelIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-brand" />
              <Input
                placeholder="e.g. Taj Palace, Lemon Tree, OYO Townhouse"
                value={hotelName}
                onChange={(e) => setHotelName(e.target.value)}
                className="pl-9 h-11 rounded-lg border-soft"
                data-testid="hotel-name-input"
              />
            </div>
          </div>

          {/* Check-in / Check-out */}
          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Check-in</label>
              <Input
                type="date" value={checkIn} min={todayStr()}
                onChange={(e) => setCheckIn(e.target.value)}
                className="mt-1 h-11 rounded-lg border-soft font-mono text-sm"
                data-testid="hotel-checkin-input"
              />
              <div className="mt-1 text-[10px] text-emerald-600 font-semibold">Today (auto)</div>
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Check-out</label>
              <Input
                type="date" value={checkOut} min={addDays(checkIn, 1)}
                onChange={(e) => setCheckOut(e.target.value)}
                className="mt-1 h-11 rounded-lg border-soft font-mono text-sm"
                data-testid="hotel-checkout-input"
              />
              <div className="mt-1 text-[10px] text-slate-400">Pick from calendar</div>
            </div>
          </div>

          {/* Per night rate */}
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Per-night rate (₹)</label>
            <Input
              type="number" min="0" step="1" placeholder="0"
              value={perNight} onChange={(e) => setPerNight(e.target.value)}
              className="mt-1 h-12 rounded-lg border-soft font-mono text-lg font-bold text-navy"
              data-testid="hotel-rate-input"
            />
          </div>
        </div>
      </div>

      {/* Summary card */}
      <div className="rounded-2xl bg-navy text-white p-4 relative overflow-hidden" data-testid="hotel-summary">
        <Moon className="absolute -right-4 -bottom-4 w-24 h-24 text-white/5" strokeWidth={1} />
        <div className="relative">
          <div className="text-[10px] uppercase tracking-[0.25em] text-lime font-bold">Booking Summary</div>
          <div className="mt-3 space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-white/60">Nights</span>
              <span className="font-bold font-mono" data-testid="summary-nights">{nights} {nights === 1 ? 'night' : 'nights'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-white/60">Room</span>
              <span className="font-semibold">{roomType}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-white/60">Rate</span>
              <span className="font-mono">₹ {rate.toFixed(2)} <span className="text-white/40">/ night</span></span>
            </div>
            <div className="border-t border-white/10 pt-2 mt-2 flex justify-between items-end">
              <span className="text-xs text-lime uppercase tracking-wider font-bold">Total</span>
              <span className="font-mono text-2xl font-bold" data-testid="summary-total">₹ {total.toFixed(2)}</span>
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
          placeholder='e.g. "Client meeting trip — 2 night stay"'
          value={notes} onChange={(e) => setNotes(e.target.value)}
          className="mt-3 rounded-lg border-soft min-h-[64px] text-sm"
          data-testid="notes-textarea"
          maxLength={500}
        />
      </div>

      {/* GPS */}
      <div className="flat-card p-3.5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <MapPin className={`w-4 h-4 ${geo.status === 'ok' ? 'text-emerald-500' : 'text-slate-400'}`} />
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Hotel Location</div>
            {geo.status === 'ok' && geo.lat ? (
              <div className="text-[11px] text-navy font-mono">{geo.lat.toFixed(5)}, {geo.lng.toFixed(5)}</div>
            ) : geo.status === 'loading' ? (
              <div className="text-[11px] text-slate-400 inline-flex items-center gap-1"><Loader2 className="w-2.5 h-2.5 animate-spin" /> Capturing GPS…</div>
            ) : (
              <div className="text-[11px] text-slate-400">{geo.status === 'denied' ? 'Permission denied' : 'Not captured'}</div>
            )}
          </div>
        </div>
        <button onClick={captureLocation} data-testid="hotel-gps-refresh"
          className="press-down inline-flex items-center gap-1.5 h-8 px-3 rounded-full bg-brand/10 text-brand text-xs font-bold">
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>

      {/* Sticky pay-now bar */}
      <div className="fixed bottom-14 left-0 right-0 z-20 backdrop-blur-xl bg-white/95 border-t border-soft">
        <div className="max-w-screen-sm mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-bold">Total</div>
            <div className="font-mono text-xl font-bold text-navy" data-testid="bottom-bar-total">
              ₹ {total.toFixed(2)}
            </div>
          </div>
          <Button onClick={proceed} disabled={total <= 0}
            className="press-down h-12 px-6 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
            data-testid="proceed-to-pay-btn">
            Pay Now <ArrowRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      </div>
    </div>
  );
}
