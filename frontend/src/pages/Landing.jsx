import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ScanLine, QrCode, FileText, Wallet, Sparkles, ArrowRight, Check,
  Building2, ShieldCheck, Smartphone, Send, Eye, Target, Zap, HeartHandshake, Scale,
  Camera, MapPin, CheckCircle2, Download, IndianRupee, Utensils, Bike, Car, Plane, Route,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import api from '@/lib/api';
import { useAuth } from '@/lib/auth';

const Section = ({ children, className = '', id }) => (
  <section id={id} className={`px-5 md:px-10 lg:px-20 ${className}`}>{children}</section>
);

const Pill = ({ children, dark = false }) => (
  <span
    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold tracking-wide uppercase ${
      dark ? 'bg-white/10 text-lime border border-white/10' : 'bg-[#0A1128]/5 text-[#0A1128]'
    }`}
  >{children}</span>
);

/* ------------------------------------------------------------------
   PhoneShowcase — animated mobile app preview in a phone frame.
   Auto-cycles through 4 app screens with a smooth tilt + slide motion.
------------------------------------------------------------------- */
const ScreenBill = () => (
  <div className="absolute inset-0 bg-white flex flex-col">
    <div className="bg-navy px-5 pt-5 pb-9 text-white">
      <div className="flex items-center justify-between">
        <span className="text-[9px] tracking-[0.3em] text-lime/80">WALLET</span>
        <Wallet className="w-3.5 h-3.5 text-lime" />
      </div>
      <div className="font-mono text-3xl mt-1.5">₹ 248.00</div>
      <div className="text-[10px] text-white/50 mt-1">Available balance</div>
    </div>
    <div className="-mt-5 px-3.5 space-y-2 flex-1 overflow-hidden">
      {[
        { l: 'Roti', q: 3, p: 15, e: '🫓' },
        { l: 'Dal Tadka', q: 1, p: 50, e: '🍛' },
        { l: 'Rice', q: 1, p: 50, e: '🍚' },
        { l: 'Sabji', q: 1, p: 60, e: '🥘' },
      ].map((i) => (
        <div key={i.l} className="bg-white border border-soft rounded-xl px-3 py-2 flex items-center gap-2.5">
          <div className="w-7 h-7 grid place-items-center bg-lime/15 rounded-lg text-sm">{i.e}</div>
          <div className="flex-1">
            <div className="text-xs font-semibold text-navy">{i.l}</div>
            <div className="text-[9px] text-slate-400 font-mono">QTY × {i.q}</div>
          </div>
          <div className="font-mono text-xs text-navy">₹{i.p * i.q}</div>
        </div>
      ))}
      <div className="px-3 py-2.5 bg-lime rounded-xl flex items-center justify-between">
        <span className="text-[10px] font-bold tracking-wider text-navy">TOTAL</span>
        <span className="font-mono font-bold text-navy text-sm">₹ 175.00</span>
      </div>
    </div>
  </div>
);

const ScreenAIDetect = () => (
  <div className="absolute inset-0 bg-[#0A1128] flex flex-col text-white">
    <div className="px-4 pt-4 pb-3 flex items-center justify-between border-b border-white/10">
      <div className="flex items-center gap-1.5">
        <Sparkles className="w-3.5 h-3.5 text-lime" />
        <span className="text-[10px] tracking-[0.2em] uppercase font-semibold">AI Snap</span>
      </div>
      <span className="text-[9px] text-lime/70 font-mono">DETECTING…</span>
    </div>
    <div className="relative flex-1 m-3 rounded-2xl overflow-hidden bg-gradient-to-br from-amber-900/60 to-red-900/60 border border-white/10">
      <img
        src="https://images.unsplash.com/photo-1631452180519-c014fe946bc7?w=400"
        alt="thali"
        className="absolute inset-0 w-full h-full object-cover opacity-90"
        onError={(e) => { e.currentTarget.style.display = 'none'; }}
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />
      {/* AI scan lines */}
      <motion.div
        className="absolute left-0 right-0 h-[2px] bg-lime shadow-[0_0_12px_2px_rgba(212,255,0,0.7)]"
        animate={{ top: ['10%', '90%', '10%'] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
      />
      {/* detection boxes */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.3 }}
        className="absolute top-[18%] left-[12%] w-10 h-8 border-2 border-lime rounded"
      >
        <span className="absolute -top-4 left-0 text-[8px] font-mono bg-lime text-navy px-1 rounded-sm">Roti</span>
      </motion.div>
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.6 }}
        className="absolute top-[40%] right-[18%] w-12 h-10 border-2 border-lime rounded"
      >
        <span className="absolute -top-4 right-0 text-[8px] font-mono bg-lime text-navy px-1 rounded-sm">Dal</span>
      </motion.div>
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.9 }}
        className="absolute bottom-[22%] left-[28%] w-12 h-9 border-2 border-lime rounded"
      >
        <span className="absolute -top-4 left-0 text-[8px] font-mono bg-lime text-navy px-1 rounded-sm">Sabji</span>
      </motion.div>
    </div>
    <div className="px-4 pb-4 pt-2">
      <div className="flex items-center justify-between text-[10px] mb-2">
        <span className="text-white/60">3 items found</span>
        <span className="text-lime font-mono">98% match</span>
      </div>
      <div className="bg-lime text-navy rounded-xl py-2.5 text-center text-xs font-bold">
        <Camera className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Confirm & Continue
      </div>
    </div>
  </div>
);

const ScreenUPIScan = () => (
  <div className="absolute inset-0 bg-[#0A1128] flex flex-col text-white">
    <div className="px-4 pt-4 pb-3 flex items-center justify-between">
      <div className="flex items-center gap-1.5">
        <QrCode className="w-3.5 h-3.5 text-lime" />
        <span className="text-[10px] tracking-[0.2em] uppercase font-semibold">Scan UPI QR</span>
      </div>
      <span className="text-[9px] text-white/40 font-mono">STEP 2 / 3</span>
    </div>
    <div className="px-3 text-center">
      <div className="text-[10px] text-white/50">Paying to</div>
      <div className="font-display font-bold text-sm mt-0.5">Sharma Restaurant</div>
      <div className="font-mono text-lime text-lg mt-1">₹ 175.00</div>
    </div>
    <div className="relative flex-1 m-3 rounded-2xl overflow-hidden bg-black border border-white/10 grid place-items-center">
      {/* QR mock */}
      <div className="w-32 h-32 bg-white rounded-lg p-2 relative">
        <div className="grid grid-cols-8 grid-rows-8 gap-[2px] w-full h-full">
          {Array.from({ length: 64 }).map((_, i) => (
            <div key={i} className={`${[0,1,6,7,8,9,14,15,16,22,23,40,41,46,47,48,49,54,55,56,57,62,63,18,28,35,42,53,33,20,11,4,5,12,19,26,27,34,43,50,51,58,59,38,29,21,13,30,37,44].includes(i) ? 'bg-navy' : 'bg-white'} rounded-[1px]`} />
          ))}
        </div>
        {/* finder squares */}
        <div className="absolute top-2 left-2 w-5 h-5 border-[3px] border-navy rounded-sm" />
        <div className="absolute top-2 right-2 w-5 h-5 border-[3px] border-navy rounded-sm" />
        <div className="absolute bottom-2 left-2 w-5 h-5 border-[3px] border-navy rounded-sm" />
      </div>
      {/* scanning corner brackets */}
      <div className="absolute top-6 left-6 w-6 h-6 border-l-2 border-t-2 border-lime" />
      <div className="absolute top-6 right-6 w-6 h-6 border-r-2 border-t-2 border-lime" />
      <div className="absolute bottom-6 left-6 w-6 h-6 border-l-2 border-b-2 border-lime" />
      <div className="absolute bottom-6 right-6 w-6 h-6 border-r-2 border-b-2 border-lime" />
      {/* scan line */}
      <motion.div
        className="absolute left-8 right-8 h-[2px] bg-lime shadow-[0_0_12px_2px_rgba(212,255,0,0.7)]"
        animate={{ top: ['15%', '85%', '15%'] }}
        transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
      />
    </div>
    <div className="px-4 pb-4 grid grid-cols-3 gap-1.5">
      {['GPay', 'PhonePe', 'Paytm'].map((a) => (
        <div key={a} className="bg-white/5 border border-white/10 rounded-lg py-1.5 text-center text-[9px] font-semibold">{a}</div>
      ))}
    </div>
  </div>
);

const ScreenInvoice = () => (
  <div className="absolute inset-0 bg-white flex flex-col">
    <div className="bg-lime px-4 pt-5 pb-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[9px] tracking-[0.3em] font-bold text-navy">INVOICE</div>
          <div className="font-display font-bold text-navy text-base mt-0.5">Bill #B4P-8421</div>
        </div>
        <motion.div
          initial={{ scale: 0, rotate: -45 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: 'spring', stiffness: 200, delay: 0.2 }}
          className="w-9 h-9 rounded-full bg-navy grid place-items-center"
        >
          <CheckCircle2 className="w-5 h-5 text-lime" />
        </motion.div>
      </div>
    </div>
    <div className="px-4 pt-3 pb-2 border-b border-soft">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[9px] text-slate-500">
          <MapPin className="w-3 h-3" /> Indore, MP
        </div>
        <div className="text-[9px] font-mono text-slate-500">2026-02-28 14:32</div>
      </div>
      <div className="mt-1.5">
        <div className="text-[9px] text-slate-400 uppercase tracking-wider">Merchant</div>
        <div className="text-xs font-semibold text-navy">Sharma Restaurant</div>
        <div className="text-[9px] text-slate-400 font-mono">sharma@paytm</div>
      </div>
    </div>
    <div className="px-4 py-2 flex-1 space-y-1">
      {[
        { l: 'Roti × 3', p: 45 },
        { l: 'Dal Tadka', p: 50 },
        { l: 'Rice', p: 50 },
        { l: 'Sabji', p: 30 },
      ].map((i) => (
        <div key={i.l} className="flex items-center justify-between text-[10px] py-1 border-b border-dashed border-slate-200">
          <span className="text-navy">{i.l}</span>
          <span className="font-mono text-navy">₹{i.p}</span>
        </div>
      ))}
      <div className="flex items-center justify-between pt-2 mt-1">
        <span className="text-[10px] font-bold tracking-wider text-navy">TOTAL</span>
        <span className="font-mono font-bold text-navy">₹ 175.00</span>
      </div>
    </div>
    <div className="px-4 pb-4 grid grid-cols-2 gap-2">
      <div className="bg-white border border-navy rounded-lg py-2 text-center text-[9px] font-bold text-navy">
        <Download className="w-3 h-3 inline -mt-0.5 mr-1" /> PDF
      </div>
      <div className="bg-navy rounded-lg py-2 text-center text-[9px] font-bold text-lime">
        <Send className="w-3 h-3 inline -mt-0.5 mr-1" /> Send
      </div>
    </div>
  </div>
);

const ScreenAutoFare = () => (
  <div className="absolute inset-0 bg-white flex flex-col">
    <div className="bg-[#FFC83D] px-4 pt-5 pb-4 relative overflow-hidden">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Car className="w-3.5 h-3.5 text-navy" />
          <span className="text-[10px] tracking-[0.25em] uppercase font-bold text-navy">Auto Ride</span>
        </div>
        <span className="text-[9px] font-mono text-navy/70">FARE · ₹</span>
      </div>
      <div className="font-mono font-bold text-3xl text-navy mt-1.5">₹ 450.00</div>
      <div className="text-[10px] text-navy/70 mt-0.5">Rajiv Chowk → Gurugram</div>
      {/* moving auto silhouette */}
      <motion.div
        className="absolute -bottom-1 text-2xl"
        animate={{ x: ['-20%', '110%'] }}
        transition={{ duration: 3.4, repeat: Infinity, ease: 'linear' }}
      >🛺</motion.div>
    </div>
    <div className="px-3.5 py-3 flex-1 space-y-2">
      <div className="bg-white border border-soft rounded-xl p-3 flex items-center gap-3">
        <div className="w-7 h-7 grid place-items-center bg-lime/20 rounded-lg"><MapPin className="w-3.5 h-3.5 text-navy" /></div>
        <div className="flex-1">
          <div className="text-[9px] uppercase tracking-wider text-slate-400">From</div>
          <div className="text-xs font-semibold text-navy">Rajiv Chowk, Delhi</div>
        </div>
      </div>
      <div className="bg-white border border-soft rounded-xl p-3 flex items-center gap-3">
        <div className="w-7 h-7 grid place-items-center bg-brand/15 rounded-lg"><MapPin className="w-3.5 h-3.5 text-brand" /></div>
        <div className="flex-1">
          <div className="text-[9px] uppercase tracking-wider text-slate-400">To</div>
          <div className="text-xs font-semibold text-navy">Gurugram</div>
        </div>
      </div>
      <div className="flex items-center justify-between text-[10px] py-1">
        <span className="text-slate-500">Distance · 30.0 km</span>
        <span className="font-mono text-navy">₹ 15/km</span>
      </div>
    </div>
    <div className="px-3.5 pb-4">
      <div className="px-3 py-2.5 bg-navy rounded-xl flex items-center justify-between">
        <span className="text-[10px] font-bold tracking-wider text-lime">FARE TOTAL</span>
        <span className="font-mono font-bold text-lime text-sm">₹ 450.00</span>
      </div>
    </div>
  </div>
);

const ScreenBikeFuel = () => (
  <div className="absolute inset-0 bg-[#0A1128] flex flex-col text-white">
    <div className="px-4 pt-4 pb-2 flex items-center justify-between border-b border-white/10">
      <div className="flex items-center gap-1.5">
        <Bike className="w-3.5 h-3.5 text-lime" />
        <span className="text-[10px] tracking-[0.25em] uppercase font-bold">Bike · Fuel</span>
      </div>
      <span className="text-[9px] text-lime/80 font-mono">OCR ✓</span>
    </div>
    <div className="relative flex-1 m-3 rounded-2xl overflow-hidden bg-gradient-to-br from-orange-600/40 to-red-700/40 border border-white/10">
      <img
        src="https://images.unsplash.com/photo-1545262810-77515befe149?w=400"
        alt="fuel pump"
        className="absolute inset-0 w-full h-full object-cover opacity-90"
        onError={(e) => { e.currentTarget.style.display = 'none'; }}
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent" />
      {/* OCR scan beam */}
      <motion.div
        className="absolute left-0 right-0 h-[2px] bg-lime shadow-[0_0_14px_2px_rgba(212,255,0,0.7)]"
        animate={{ top: ['8%', '92%', '8%'] }}
        transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
      />
      {/* moving bike silhouette */}
      <motion.div
        className="absolute bottom-3 text-2xl drop-shadow"
        animate={{ x: ['-15%', '115%'] }}
        transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
      >🏍️</motion.div>
      {/* OCR detection chip */}
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="absolute top-3 left-3 bg-lime text-navy px-2 py-0.5 rounded-sm text-[8px] font-mono font-bold"
      >PETROL · 2.1 L</motion.div>
    </div>
    <div className="px-4 pb-2 grid grid-cols-3 gap-2 text-center">
      <div className="bg-white/5 border border-white/10 rounded-lg py-1.5">
        <div className="text-[8px] text-white/50 uppercase tracking-wider">Litres</div>
        <div className="font-mono text-sm text-lime">2.10</div>
      </div>
      <div className="bg-white/5 border border-white/10 rounded-lg py-1.5">
        <div className="text-[8px] text-white/50 uppercase tracking-wider">Rate</div>
        <div className="font-mono text-sm">₹104.7</div>
      </div>
      <div className="bg-white/5 border border-white/10 rounded-lg py-1.5">
        <div className="text-[8px] text-white/50 uppercase tracking-wider">Total</div>
        <div className="font-mono text-sm text-lime">₹220</div>
      </div>
    </div>
    <div className="px-4 pb-4 pt-2">
      <div className="bg-lime text-navy rounded-xl py-2.5 text-center text-xs font-bold">
        <CheckCircle2 className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Use as expense
      </div>
    </div>
  </div>
);

const ScreenTravelBill = () => (
  <div className="absolute inset-0 bg-white flex flex-col">
    {/* Header — boarding pass style */}
    <div className="bg-navy px-4 pt-5 pb-4 relative overflow-hidden">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Plane className="w-3.5 h-3.5 text-lime" />
          <span className="text-[10px] tracking-[0.25em] uppercase font-bold text-lime">Travel Bill</span>
        </div>
        <span className="text-[9px] font-mono text-white/50">B4P-TRV-7042</span>
      </div>
      {/* From → To */}
      <div className="mt-3 flex items-end justify-between text-white">
        <div>
          <div className="text-[9px] text-white/50 uppercase tracking-wider">From</div>
          <div className="font-display font-black text-2xl leading-none">DEL</div>
          <div className="text-[9px] text-white/60 mt-0.5">Delhi · 06:40</div>
        </div>
        <div className="flex-1 px-2 relative">
          <div className="border-t border-dashed border-lime/60 relative">
            <motion.div
              className="absolute -top-2 text-lime"
              animate={{ x: ['-10%', '110%'] }}
              transition={{ duration: 3.2, repeat: Infinity, ease: 'linear' }}
            >
              <Plane className="w-3.5 h-3.5 rotate-90" />
            </motion.div>
          </div>
          <div className="text-center text-[8px] text-white/40 font-mono mt-1">2h 10m · IndiGo</div>
        </div>
        <div className="text-right">
          <div className="text-[9px] text-white/50 uppercase tracking-wider">To</div>
          <div className="font-display font-black text-2xl leading-none">BLR</div>
          <div className="text-[9px] text-white/60 mt-0.5">Bengaluru · 08:50</div>
        </div>
      </div>
    </div>

    {/* perforation */}
    <div className="relative h-2 bg-navy">
      <div className="absolute -left-1 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white" />
      <div className="absolute -right-1 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white" />
    </div>

    {/* Trip summary */}
    <div className="px-4 pt-2.5 pb-2 border-b border-soft grid grid-cols-3 gap-2">
      <div>
        <div className="text-[8px] uppercase tracking-wider text-slate-400">Date</div>
        <div className="text-[10px] font-semibold text-navy font-mono mt-0.5">28 Feb 2026</div>
      </div>
      <div>
        <div className="text-[8px] uppercase tracking-wider text-slate-400">PAX</div>
        <div className="text-[10px] font-semibold text-navy mt-0.5">1 Adult</div>
      </div>
      <div>
        <div className="text-[8px] uppercase tracking-wider text-slate-400">Class</div>
        <div className="text-[10px] font-semibold text-navy mt-0.5">Economy</div>
      </div>
    </div>

    {/* Fare breakdown */}
    <div className="px-4 py-2 flex-1 space-y-1">
      {[
        { l: 'Base fare', p: 3850 },
        { l: 'Taxes & fees', p: 612 },
        { l: 'Cab · Airport ↔ Office', p: 380 },
      ].map((i) => (
        <div key={i.l} className="flex items-center justify-between text-[10px] py-1 border-b border-dashed border-slate-200">
          <span className="text-navy flex items-center gap-1.5">
            <Route className="w-3 h-3 text-slate-400" /> {i.l}
          </span>
          <span className="font-mono text-navy">₹{i.p.toLocaleString('en-IN')}</span>
        </div>
      ))}
      <div className="flex items-center justify-between pt-2 mt-1">
        <span className="text-[10px] font-bold tracking-wider text-navy">REIMBURSE</span>
        <span className="font-mono font-bold text-navy text-sm">₹ 4,842</span>
      </div>
    </div>

    {/* CTA */}
    <div className="px-4 pb-4 grid grid-cols-2 gap-2">
      <div className="bg-white border border-navy rounded-lg py-2 text-center text-[9px] font-bold text-navy">
        <Download className="w-3 h-3 inline -mt-0.5 mr-1" /> PDF
      </div>
      <div className="bg-lime rounded-lg py-2 text-center text-[9px] font-bold text-navy">
        <Send className="w-3 h-3 inline -mt-0.5 mr-1" /> Send to HR
      </div>
    </div>
  </div>
);

const PHONE_SCREENS = [
  { key: 'bill', label: 'Food · Itemised bill', el: <ScreenBill /> },
  { key: 'ai', label: 'AI thali scan', el: <ScreenAIDetect /> },
  { key: 'travel', label: 'Travel · Flight bill', el: <ScreenTravelBill /> },
  { key: 'auto', label: 'Auto · Ride fare', el: <ScreenAutoFare /> },
  { key: 'bike', label: 'Bike · Fuel slip', el: <ScreenBikeFuel /> },
  { key: 'upi', label: 'UPI QR pay', el: <ScreenUPIScan /> },
  { key: 'invoice', label: 'PDF invoice', el: <ScreenInvoice /> },
];

const PhoneShowcase = () => {
  const [active, setActive] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setActive((a) => (a + 1) % PHONE_SCREENS.length), 3200);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="relative mx-auto w-[280px] sm:w-[300px] lg:w-[320px]" data-testid="hero-phone-showcase">
      {/* ambient glow */}
      <motion.div
        className="absolute -inset-10 rounded-[3rem] bg-lime/15 blur-3xl"
        animate={{ opacity: [0.4, 0.7, 0.4] }}
        transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* floating accent pill — left */}
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.5 }}
        className="absolute -left-8 top-16 z-20 hidden sm:flex items-center gap-1.5 bg-white text-navy px-3 py-1.5 rounded-full shadow-xl border border-soft"
      >
        <Sparkles className="w-3.5 h-3.5 text-brand" />
        <span className="text-[10px] font-bold uppercase tracking-wider">AI Detected</span>
      </motion.div>

      {/* floating accent pill — right */}
      <motion.div
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.7 }}
        className="absolute -right-6 bottom-24 z-20 hidden sm:flex items-center gap-1.5 bg-lime text-navy px-3 py-1.5 rounded-full shadow-xl"
      >
        <IndianRupee className="w-3.5 h-3.5" />
        <span className="text-[10px] font-bold uppercase tracking-wider">₹5 = 1 Bill</span>
      </motion.div>

      {/* phone frame — tilted */}
      <motion.div
        animate={{ rotate: [-3, -1.5, -3] }}
        transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
        className="relative"
      >
        <div className="relative bg-[#0F1740] border border-white/10 rounded-[2.4rem] p-2.5 shadow-2xl">
          {/* notch */}
          <div className="absolute top-3 left-1/2 -translate-x-1/2 w-20 h-5 bg-black rounded-full z-30" />

          <div className="relative bg-white rounded-[2rem] overflow-hidden aspect-[9/19]">
            {PHONE_SCREENS.map((s, i) => (
              <motion.div
                key={s.key}
                initial={false}
                animate={{
                  opacity: i === active ? 1 : 0,
                  y: i === active ? 0 : i < active ? -30 : 30,
                  scale: i === active ? 1 : 0.96,
                }}
                transition={{ duration: 0.6, ease: 'easeInOut' }}
                className="absolute inset-0"
                style={{ pointerEvents: i === active ? 'auto' : 'none' }}
              >
                {s.el}
              </motion.div>
            ))}
          </div>
        </div>
      </motion.div>

      {/* progress dots */}
      <div className="mt-5 flex items-center justify-center gap-2">
        {PHONE_SCREENS.map((s, i) => (
          <button
            key={s.key}
            onClick={() => setActive(i)}
            data-testid={`phone-dot-${s.key}`}
            className="relative h-1.5 rounded-full transition-all"
            style={{ width: i === active ? 28 : 8, background: i === active ? '#FFC02C' : 'rgba(255,255,255,0.25)' }}
            aria-label={s.label}
          />
        ))}
      </div>
      <div className="mt-2 text-center text-[10px] uppercase tracking-[0.25em] text-white/40 font-semibold">
        {PHONE_SCREENS[active].label}
      </div>
    </div>
  );
};

const Hero = () => {
  const nav = useNavigate();
  const { user } = useAuth();
  return (
    <div className="relative overflow-hidden bg-navy text-white">
      <div
        className="absolute inset-0 opacity-30"
        style={{
          background:
            'radial-gradient(circle at 20% 20%, rgba(212,255,0,0.18), transparent 40%), radial-gradient(circle at 80% 60%, rgba(212,255,0,0.10), transparent 50%)',
        }}
      />
      <Section className="relative pt-20 pb-24 md:pt-28 md:pb-32">
        <div className="grid lg:grid-cols-12 gap-12 items-center">
          <div className="lg:col-span-7">
            <h1 className="font-display font-bold text-4xl sm:text-5xl lg:text-7xl tracking-tight leading-[1.05]">
              Pay your bill.<br />
              <span className="text-lime">Generate</span> the invoice.<br />
              Done in 60 seconds.
            </h1>
            <p className="mt-6 text-base sm:text-lg text-white/70 max-w-xl leading-relaxed">
              BILL4PE turns every UPI payment into a corporate-ready reimbursement invoice using
              AI vision. Snap a photo. Scan a QR. Get a PDF. Built for the modern Indian workforce.
            </p>
            <div className="mt-10 flex flex-wrap gap-3">
              <button
                onClick={() => nav(user ? '/app' : '/register')}
                data-testid="hero-cta-launch"
                className="press-down inline-flex items-center gap-2 bg-brand text-white font-semibold px-6 py-3.5 rounded-full hover:bg-[#1858CC]"
              >
                Launch BILL4PE <ArrowRight className="w-4 h-4" />
              </button>
              <a
                href="#how"
                className="press-down inline-flex items-center gap-2 border border-white/20 text-white px-6 py-3.5 rounded-full hover:bg-white/5"
                data-testid="hero-cta-how"
              >
                How it works
              </a>
            </div>
            <div className="mt-10 flex items-center gap-5 text-xs text-white/60">
              <div className="flex items-center gap-1.5"><Check className="w-3.5 h-3.5 text-lime" /> No setup</div>
              <div className="flex items-center gap-1.5"><Check className="w-3.5 h-3.5 text-lime" /> Works offline</div>
              <div className="flex items-center gap-1.5"><Check className="w-3.5 h-3.5 text-lime" /> Install as PWA</div>
            </div>
          </div>

          <motion.div
            initial={{ y: 30, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.7, ease: 'easeOut' }}
            className="lg:col-span-5 relative"
          >
            <PhoneShowcase />
          </motion.div>
        </div>
      </Section>

      {/* trust strip */}
      <div className="border-t border-white/10 bg-black">
        <div className="overflow-hidden">
          <div className="marquee py-5 text-white text-xs uppercase tracking-[0.4em] font-semibold">
            {[...Array(2)].map((_, k) => (
              <div key={k} className="flex gap-12 items-center pr-12">
                <span>Built for India</span><span>·</span>
                <span>UPI Ready</span><span>·</span>
                <span>AI Powered</span><span>·</span>
                <span>Corporate Reimbursement</span><span>·</span>
                <span>Mobile First</span><span>·</span>
                <span>PWA Installable</span><span>·</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const HowItWorks = () => {
  const steps = [
    { icon: ScanLine, t: 'Snap or Type', d: 'Take a photo of your meal or receipt. AI detects every item and price automatically. Or type it in manually with smart suggestions.' },
    { icon: QrCode, t: 'Scan UPI QR', d: 'Tap Pay Now. Scan any merchant QR — GPay, PhonePe, Paytm, BharatPe. We auto-capture merchant name, UPI ID and txn details.' },
    { icon: FileText, t: 'Get the Invoice', d: '₹5 from wallet generates a professional PDF reimbursement invoice. Share it, download it, file your expense.' },
  ];
  return (
    <Section id="how" className="py-24 bg-white">
      <div className="max-w-3xl">
        <Pill>How it works</Pill>
        <h2 className="font-display text-3xl sm:text-5xl font-bold mt-4 tracking-tight text-navy">
          Three taps to a reimbursement-ready invoice.
        </h2>
      </div>
      <div className="grid md:grid-cols-3 gap-5 mt-14">
        {steps.map((s, i) => {
          const Icon = s.icon;
          return (
            <div key={s.t} className="flat-card p-7 relative overflow-hidden group">
              <div className="font-mono text-xs text-slate-400">STEP / 0{i + 1}</div>
              <Icon className="w-9 h-9 text-navy mt-4" strokeWidth={1.6} />
              <h3 className="font-display font-bold text-xl mt-5 text-navy">{s.t}</h3>
              <p className="text-sm text-slate-500 mt-2 leading-relaxed">{s.d}</p>
              <div className="absolute right-5 bottom-5 w-2 h-2 rounded-full bg-lime opacity-0 group-hover:opacity-100 transition" />
            </div>
          );
        })}
      </div>
    </Section>
  );
};

const Features = () => {
  const feats = [
    { icon: QrCode, t: 'Universal UPI', d: 'Works with every Indian UPI app and generic QR.' },
    { icon: ScanLine, t: 'AI Vision', d: 'Gemini-powered item detection with price estimation.' },
    { icon: FileText, t: 'Smart Invoice', d: 'Corporate-grade PDF, downloadable & shareable.' },
    { icon: Wallet, t: 'Wallet System', d: 'Recharge once. Pay platform charges seamlessly.' },
    { icon: ShieldCheck, t: 'Reimbursement Ready', d: 'Auto geo-tag, timestamps, txn IDs preserved.' },
    { icon: Smartphone, t: 'Install as App', d: 'PWA. Works offline. No app store needed.' },
  ];
  return (
    <Section className="py-24 bg-[#F4F5F7]">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <Pill>Features</Pill>
          <h2 className="font-display text-3xl sm:text-5xl font-bold mt-4 text-navy tracking-tight max-w-2xl">
            Every receipt. Every category. One workflow.
          </h2>
        </div>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-14">
        {feats.map((f) => {
          const Icon = f.icon;
          return (
            <div key={f.t} className="bg-white border border-soft rounded-2xl p-6 hover:border-navy transition">
              <Icon className="w-7 h-7 text-navy" strokeWidth={1.6} />
              <h3 className="font-display font-bold text-lg mt-5 text-navy">{f.t}</h3>
              <p className="text-sm text-slate-500 mt-1.5">{f.d}</p>
            </div>
          );
        })}
      </div>
    </Section>
  );
};

const VisionMission = () => (
  <Section className="py-24 bg-navy text-white" id="vision">
    <div className="max-w-3xl">
      <Pill dark>Why we exist</Pill>
      <h2 className="font-display text-3xl sm:text-5xl font-bold mt-4 tracking-tight">
        Smart, secure & leakage-free expense management for modern corporates.
      </h2>
    </div>

    <div className="grid md:grid-cols-3 gap-6 mt-14">
      <div className="bg-white/[0.04] border border-white/10 rounded-3xl p-8 hover:border-brand transition-colors" data-testid="vision-card">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-[0.25em] text-white bg-brand/10 border border-brand/20">
          <Eye className="w-3 h-3" /> Our Vision
        </div>
        <h3 className="font-display text-xl sm:text-2xl font-bold mt-5 tracking-tight">
          A leakage-free, AI-powered expense ecosystem for every corporate.
        </h3>
        <p
          className="mt-5 text-white leading-[1.75] text-[13.5px] hyphens-auto"
          style={{ textAlign: 'justify', textAlignLast: 'left', textJustify: 'inter-word' }}
          data-testid="vision-text"
        >
          Bill4Pe is envisioned as a smart and secure platform that transforms how corporates
          manage imprest and petty expenses. With AI-enabled self-invoicing, employees and contract
          workers can generate instant, authenticated invoices — eliminating financial leakages,
          preventing fraudulent claims, and replacing the risk of fake cash memos. Every transaction
          carries verified merchant details and embedded geolocation data, giving organizations
          real-time visibility, audit-ready documentation and total financial control.
        </p>
      </div>

      <div className="bg-white/[0.04] border border-white/10 rounded-3xl p-8 hover:border-brand transition-colors" data-testid="mission-card">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-[0.25em] text-white bg-brand/10 border border-brand/20">
          <Target className="w-3 h-3" /> Our Mission
        </div>
        <h3 className="font-display text-xl sm:text-2xl font-bold mt-5 tracking-tight">
          Instant, authenticated self-invoices for unregistered-supplier expenses.
        </h3>
        <p
          className="mt-5 text-white/70 leading-[1.75] text-[13.5px] hyphens-auto"
          style={{ textAlign: 'justify', textAlignLast: 'left', textJustify: 'inter-word' }}
          data-testid="mission-text"
        >
          To revolutionize corporate expense management by offering an AI-enabled, smart and secure
          platform that facilitates the instant generation of self-invoices for expenses incurred
          from unregistered suppliers who do not provide authenticated or acceptable bills. We are
          committed to transparency, accuracy and fraud prevention through verified data, merchant
          details and geolocation tracking — collaborating with individuals and corporates to promote
          genuine, compliant self-invoicing practices.
        </p>
      </div>

      <div className="bg-white/[0.04] border border-white/10 rounded-3xl p-8 hover:border-brand transition-colors" data-testid="ethics-card">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-[0.25em] text-white bg-brand/10 border border-brand/20">
          <Scale className="w-3 h-3" /> Our Ethics
        </div>
        <h3 className="font-display text-xl sm:text-2xl font-bold mt-5 tracking-tight">
          Integrity, transparency & accountability — by design.
        </h3>
        <p
          className="mt-5 text-white leading-[1.75] text-[13.5px] hyphens-auto"
          style={{ textAlign: 'justify', textAlignLast: 'left', textJustify: 'inter-word' }}
          data-testid="ethics-text"
        >
          Bill4Pe is committed to upholding the highest standards of integrity, transparency and
          accountability in corporate expense management. Our ethical foundation enables the
          generation of genuine, leakage-free and compliant self-invoices through an AI-enabled,
          secure platform. Every expense incurred during official activities is accurately recorded
          and supported with reliable data — including geolocation tracking — for authenticity and
          traceability. We promote trust, eliminate misuse and foster responsible financial practices
          that benefit organizations and their stakeholders alike.
        </p>
      </div>
    </div>

    {/* Core values */}
    <div className="mt-14">
      <Pill dark>Our values</Pill>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
        {[
          { icon: Zap, t: 'Speed first', d: 'If it takes more than 60 seconds, we did it wrong.' },
          { icon: ShieldCheck, t: 'Audit-ready', d: 'Every bill carries merchant, txn, geo and time.' },
          { icon: Sparkles, t: 'AI-native', d: 'Vision and language models do the boring work.' },
          { icon: HeartHandshake, t: 'Made for India', d: 'UPI, rupees, Indian food, real merchant flows.' },
        ].map(({ icon: Icon, t, d }) => (
          <div key={t} className="bg-white/[0.03] border border-white/10 rounded-2xl p-5">
            <Icon className="w-6 h-6 text-brand" strokeWidth={1.6} />
            <div className="font-display font-bold mt-4">{t}</div>
            <div className="text-xs text-white/50 mt-1.5 leading-relaxed">{d}</div>
          </div>
        ))}
      </div>
    </div>
  </Section>
);

const UseCases = () => {
  const items = [
    { t: 'Sales & Field Teams', d: 'Track every meal, ride and client gift with proof.' },
    { t: 'Consultants', d: 'Generate billable expense reports per client in minutes.' },
    { t: 'Startups', d: 'Replace your messy receipts WhatsApp group.' },
    { t: 'Enterprises', d: 'Stream-line corporate expense policies with API access.' },
  ];
  return (
    <Section className="py-24 bg-white">
      <Pill>Use cases</Pill>
      <h2 className="font-display text-3xl sm:text-5xl font-bold mt-4 text-navy tracking-tight max-w-3xl">
        Built for everyone who spends company money.
      </h2>
      <div className="grid md:grid-cols-2 gap-4 mt-12">
        {items.map((i) => (
          <div key={i.t} className="flat-card p-7 flex items-start gap-5">
            <Building2 className="w-7 h-7 text-navy shrink-0 mt-1" strokeWidth={1.6} />
            <div>
              <h3 className="font-display font-bold text-xl text-navy">{i.t}</h3>
              <p className="text-sm text-slate-500 mt-1.5">{i.d}</p>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
};

const Testimonials = () => {
  const quotes = [
    { n: 'Ananya R.', r: 'Sales Lead, Bengaluru', q: 'My expense reports now take 5 minutes instead of 2 hours.' },
    { n: 'Vikram S.', r: 'Founder, Mumbai', q: 'Our team finally has a single source of truth for reimbursements.' },
    { n: 'Priya M.', r: 'Consultant, Delhi', q: 'The AI item detection is genuinely magical. It works.' },
    { n: 'Rohit K.', r: 'CFO, Pune', q: 'Cleaner audit trail, faster approvals. Replaced 3 tools.' },
  ];
  return (
    <Section className="py-24 bg-[#F4F5F7]">
      <Pill>Loved by teams</Pill>
      <h2 className="font-display text-3xl sm:text-5xl font-bold mt-4 text-navy tracking-tight max-w-2xl">
        Real users. Real reimbursements.
      </h2>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-12">
        {quotes.map((q) => (
          <div key={q.n} className="bg-white border border-soft rounded-2xl p-6">
            <p className="text-navy leading-relaxed">"{q.q}"</p>
            <div className="mt-5 flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-navy text-white grid place-items-center font-bold">
                {q.n[0]}
              </div>
              <div>
                <div className="font-semibold text-sm text-navy">{q.n}</div>
                <div className="text-xs text-slate-500">{q.r}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
};

const Contact = () => {
  const [form, setForm] = useState({ name: '', email: '', message: '' });
  const [sending, setSending] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setSending(true);
    try {
      await api.post('/contact', form);
      toast.success('Message sent. We will get back to you shortly.');
      setForm({ name: '', email: '', message: '' });
    } catch {
      toast.error('Failed to send. Try again.');
    } finally { setSending(false); }
  };
  return (
    <Section className="py-24 bg-white" id="contact">
      <div className="grid md:grid-cols-2 gap-12 items-start">
        <div>
          <Pill>Get in touch</Pill>
          <h2 className="font-display text-3xl sm:text-5xl font-bold mt-4 text-navy tracking-tight">
            Talk to the BILL4PE team.
          </h2>
          <p className="mt-5 text-slate-500 leading-relaxed">
            Partnerships, enterprise plans, or just want to say hi? Drop us a note.
            We respond within one business day.
          </p>
        </div>
        <form onSubmit={submit} className="flat-card p-7 space-y-5">
          <div>
            <label className="text-xs uppercase font-semibold tracking-wider text-slate-500">Your name</label>
            <Input
              required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="mt-2 h-12 rounded-xl"
              data-testid="contact-name-input"
            />
          </div>
          <div>
            <label className="text-xs uppercase font-semibold tracking-wider text-slate-500">Email</label>
            <Input
              required type="email" value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="mt-2 h-12 rounded-xl"
              data-testid="contact-email-input"
            />
          </div>
          <div>
            <label className="text-xs uppercase font-semibold tracking-wider text-slate-500">Message</label>
            <Textarea
              required rows={4} value={form.message}
              onChange={(e) => setForm({ ...form, message: e.target.value })}
              className="mt-2 rounded-xl"
              data-testid="contact-message-input"
            />
          </div>
          <Button
            type="submit" disabled={sending}
            className="press-down w-full h-12 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
            data-testid="contact-submit-btn"
          >
            <Send className="w-4 h-4 mr-2" /> {sending ? 'Sending...' : 'Send message'}
          </Button>
        </form>
      </div>
    </Section>
  );
};

const Footer = () => (
  <footer className="bg-black text-white px-5 md:px-10 lg:px-20 py-16">
    <div className="grid md:grid-cols-12 gap-10">
      <div className="md:col-span-7">
        <div className="bg-white inline-flex items-center p-3 rounded-2xl">
          <img src="/logo.png" alt="Bill4Pe — The Intelligent Building" className="h-24 w-auto object-contain" />
        </div>
        <p className="mt-6 text-white/50 max-w-md">
          Pay Your Bill — AI Powered Expense & Invoice Platform.
          Made for India's professionals. <span className="text-brand">www.bill4pe.com</span>
        </p>
      </div>
      <div className="md:col-span-2">
        <div className="text-xs uppercase tracking-wider text-white/40">Product</div>
        <ul className="mt-4 space-y-2 text-sm">
          <li><a href="#how" className="hover:text-brand">How it works</a></li>
          <li><Link to="/app" className="hover:text-brand">Launch app</Link></li>
        </ul>
      </div>
      <div className="md:col-span-3">
        <div className="text-xs uppercase tracking-wider text-white/40">Company</div>
        <ul className="mt-4 space-y-2 text-sm">
          <li><a href="#vision" className="hover:text-brand">Vision, Mission & Ethics</a></li>
          <li><Link to="/contact" className="hover:text-brand">Contact</Link></li>
          <li><Link to="/privacy" className="hover:text-brand">Privacy</Link></li>
          <li><Link to="/terms" className="hover:text-brand">Terms</Link></li>
        </ul>
      </div>
    </div>
    <div className="mt-14 pt-6 border-t border-white/10 flex justify-between text-xs text-white/40">
      <div>© 2026 BILL4PE</div>
      <div>Made in India</div>
    </div>
  </footer>
);

/* ------------------------------------------------------------------
   MobileLanding — condensed, mobile-only landing page.
   Shows: hero pitch + 3 key benefits + sign-in/sign-up CTAs + tiny footer.
   Hidden on md+ screens (desktop sees the full marketing site).
------------------------------------------------------------------- */
const MobileLanding = () => {
  const nav = useNavigate();
  const { user } = useAuth();
  return (
    <div className="md:hidden min-h-screen bg-navy text-white relative overflow-hidden flex flex-col" data-testid="mobile-landing">
      {/* ambient glow */}
      <div
        className="absolute inset-0 opacity-40 pointer-events-none"
        style={{
          background:
            'radial-gradient(circle at 15% 10%, rgba(212,255,0,0.22), transparent 45%), radial-gradient(circle at 90% 75%, rgba(24,88,204,0.25), transparent 50%)',
        }}
      />

      {/* top bar with logo */}
      <div className="relative px-5 pt-6 pb-2 flex items-center justify-between">
        <div className="bg-white inline-flex items-center px-2 py-1.5 rounded-xl" data-testid="mobile-nav-logo">
          <img src="/logo.png" alt="Bill4Pe — The Intelligent Building" className="h-12 w-auto object-contain" />
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/login"
            data-testid="mobile-nav-signin"
            className="text-xs font-semibold text-white/80 hover:text-lime px-3 py-2 rounded-full hover:bg-white/5"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            data-testid="mobile-nav-signup"
            className="press-down text-xs font-bold text-navy bg-lime hover:bg-[#BCE300] px-3.5 py-2 rounded-full"
          >
            Sign up
          </Link>
        </div>
      </div>

      {/* hero */}
      <div className="relative px-5 pt-8 pb-6">
        <Pill dark><Sparkles className="w-3 h-3" /> AI Billing for India</Pill>
        <h1 className="font-display font-bold text-4xl mt-4 tracking-tight leading-[1.05]">
          Pay your bill.<br />
          <span className="text-lime">Generate</span> the invoice.<br />
          <span className="text-white/70 text-3xl">Done in 60 seconds.</span>
        </h1>
        <p className="mt-4 text-sm text-white/65 leading-relaxed">
          Snap a meal. Scan a UPI QR. Get a reimbursement-ready PDF invoice — instantly.
        </p>
      </div>

      {/* 3 key benefits */}
      <div className="relative px-5 grid grid-cols-3 gap-2.5 mt-2">
        {[
          { icon: ScanLine, t: 'AI Snap', d: 'Items auto-detected' },
          { icon: QrCode, t: 'UPI Pay', d: 'Any merchant QR' },
          { icon: FileText, t: 'PDF Bill', d: 'Audit-ready' },
        ].map(({ icon: Icon, t, d }) => (
          <div key={t} className="bg-white/[0.04] border border-white/10 rounded-2xl p-3.5 text-center">
            <Icon className="w-5 h-5 text-lime mx-auto" strokeWidth={1.8} />
            <div className="font-display font-bold text-[13px] mt-2.5">{t}</div>
            <div className="text-[10px] text-white/50 mt-1 leading-tight">{d}</div>
          </div>
        ))}
      </div>

      {/* trust line */}
      <div className="relative px-5 mt-6 flex items-center justify-center gap-4 text-[10px] text-white/55">
        <div className="flex items-center gap-1"><Check className="w-3 h-3 text-lime" /> No setup</div>
        <div className="flex items-center gap-1"><Check className="w-3 h-3 text-lime" /> Works offline</div>
        <div className="flex items-center gap-1"><Check className="w-3 h-3 text-lime" /> Installable PWA</div>
      </div>

      {/* spacer pushes CTAs down */}
      <div className="flex-1" />

      {/* CTAs */}
      <div className="relative px-5 pb-6 pt-8 space-y-3">
        <button
          onClick={() => nav(user ? '/app' : '/register')}
          data-testid="mobile-cta-signup"
          className="press-down w-full inline-flex items-center justify-center gap-2 bg-lime text-navy font-bold px-6 py-4 rounded-full text-base"
        >
          {user ? 'Open Bill4Pe' : 'Create free account'} <ArrowRight className="w-4 h-4" />
        </button>
        <button
          onClick={() => nav('/login')}
          data-testid="mobile-cta-signin"
          className="press-down w-full inline-flex items-center justify-center gap-2 border border-white/20 text-white font-semibold px-6 py-3.5 rounded-full text-sm hover:bg-white/5"
        >
          I already have an account
        </button>
        <p className="text-center text-[10px] text-white/40 mt-3">
          By continuing you agree to our{' '}
          <Link to="/terms" className="underline hover:text-lime">Terms</Link>
          {' '}&{' '}
          <Link to="/privacy" className="underline hover:text-lime">Privacy</Link>.
        </p>
        <p className="text-center text-[10px] text-white/30 mt-1">© 2026 BILL4PE · Made in India</p>
      </div>
    </div>
  );
};

export default function Landing() {
  useEffect(() => { document.title = 'BILL4PE — AI Expense & Invoice Platform'; }, []);
  return (
    <div className="min-h-screen bg-white">
      {/* Mobile-only condensed landing */}
      <MobileLanding />

      {/* Desktop / tablet full marketing site */}
      <div className="hidden md:block">
        <nav className="absolute top-0 left-0 right-0 z-40">
          <div className="px-5 md:px-10 lg:px-20 h-16 flex items-center justify-between text-white">
            <Link to="/" data-testid="nav-logo" className="bg-white inline-flex items-center p-1.5 rounded-xl">
              <img src="/logo.png" alt="Bill4Pe — The Intelligent Building" className="h-14 w-auto object-contain" />
            </Link>
            <div className="flex items-center gap-2">
              <Link to="/login" className="hidden sm:inline-flex px-4 py-2 rounded-full hover:bg-white/10 text-sm" data-testid="nav-login">Sign in</Link>
              <Link to="/register" className="press-down px-4 py-2 rounded-full bg-lime text-navy font-semibold text-sm hover:bg-[#BCE300]" data-testid="nav-register">Get started</Link>
            </div>
          </div>
        </nav>
        <Hero />
        <HowItWorks />
        <Features />
        <VisionMission />
        <UseCases />
        <Testimonials />
        <Contact />
        <Footer />
      </div>
    </div>
  );
}
