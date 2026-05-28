import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Camera, Mic, Receipt, Sparkles, ChevronRight, X } from 'lucide-react';

const SLIDES = [
  {
    key: 'snap',
    icon: Camera,
    badge: 'AI Vision',
    title: 'Snap your thali photo',
    body: 'Show the AI a plate of food. It detects Dal, Roti, Sabji & estimates prices in seconds.',
    accent: 'lime',
  },
  {
    key: 'voice',
    icon: Mic,
    badge: 'Voice AI',
    title: 'Just speak your expense',
    body: '"Spent 250 on lunch at Saravana Bhavan." Whisper + Gemini fill the bill for you. Hindi / English / Hinglish.',
    accent: 'brand',
  },
  {
    key: 'receipt',
    icon: Receipt,
    badge: 'Receipt OCR',
    title: 'Scan any printed bill',
    body: 'Swiggy, BigBazaar, DMart, restaurant slips — AI reads merchant, items and total automatically.',
    accent: 'lime',
  },
];

const STORAGE_KEY = 'bill4pe_onboarded_v1';

export const OnboardingTour = () => {
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) setOpen(true);
    } catch { /* */ }
  }, []);

  const close = () => {
    try { localStorage.setItem(STORAGE_KEY, '1'); } catch { /* */ }
    setOpen(false);
  };

  const next = () => {
    if (idx < SLIDES.length - 1) setIdx(idx + 1);
    else close();
  };

  if (!open) return null;
  const slide = SLIDES[idx];
  const Icon = slide.icon;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        style={{ backgroundColor: 'rgba(5, 8, 22, 0.97)' }}
        className="fixed inset-0 z-[70] backdrop-blur-md grid place-items-center px-5"
        data-testid="onboarding-overlay"
      >
        <button
          onClick={close}
          className="absolute top-5 right-5 w-10 h-10 grid place-items-center bg-white/10 rounded-full text-white"
          data-testid="onboarding-close-btn"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="w-full max-w-sm text-white">
          <AnimatePresence mode="wait">
            <motion.div
              key={slide.key}
              initial={{ opacity: 0, x: 30 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -30 }}
              transition={{ duration: 0.3 }}
              className="text-center"
            >
              <div className={`mx-auto w-24 h-24 rounded-3xl grid place-items-center shadow-2xl ${
                slide.accent === 'lime'
                  ? 'bg-lime text-navy shadow-lime/20'
                  : 'bg-brand text-white shadow-brand/30'
              }`}>
                <Icon className="w-12 h-12" strokeWidth={1.8} />
              </div>

              <div className="mt-7 inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-[0.25em] bg-white/10 text-white">
                <Sparkles className="w-3 h-3 text-lime" /> {slide.badge}
              </div>
              <h2 className="font-display text-3xl font-bold mt-3 tracking-tight">
                {slide.title}
              </h2>
              <p className="text-sm text-white/70 mt-3 leading-relaxed px-2">
                {slide.body}
              </p>
            </motion.div>
          </AnimatePresence>

          {/* Dots */}
          <div className="flex items-center justify-center gap-2 mt-8" data-testid="onboarding-dots">
            {SLIDES.map((s, i) => (
              <button
                key={s.key}
                onClick={() => setIdx(i)}
                className={`h-1.5 rounded-full transition-all ${
                  i === idx ? 'w-8 bg-lime' : 'w-1.5 bg-white/30'
                }`}
                data-testid={`onboarding-dot-${i}`}
              />
            ))}
          </div>

          {/* Actions */}
          <div className="mt-6 flex items-center justify-between">
            <button
              onClick={close}
              className="text-xs text-white/50 hover:text-white/80 font-semibold tracking-wider uppercase"
              data-testid="onboarding-skip-btn"
            >
              Skip
            </button>
            <button
              onClick={next}
              data-testid="onboarding-next-btn"
              className="press-down inline-flex items-center gap-2 h-12 px-6 bg-lime text-navy rounded-full font-bold text-sm"
            >
              {idx < SLIDES.length - 1 ? 'Next' : 'Get started'}
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};

export default OnboardingTour;
