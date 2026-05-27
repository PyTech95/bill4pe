import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, X, Loader2, Sparkles, Square } from 'lucide-react';
import { toast } from 'sonner';
import api from '@/lib/api';

const MAX_SECONDS = 30;

export const VoiceExpense = () => {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState('idle'); // idle | recording | processing
  const [seconds, setSeconds] = useState(0);
  const [transcript, setTranscript] = useState('');

  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const timerRef = useRef(null);

  const cleanupRecorder = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch { /* */ }
    streamRef.current = null;
    recorderRef.current = null;
    chunksRef.current = [];
  };

  useEffect(() => () => cleanupRecorder(), []);

  const startRecording = async () => {
    setOpen(true);
    setTranscript('');
    setSeconds(0);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      toast.error('Voice recording not supported on this browser');
      setOpen(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '');
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      recorderRef.current = rec;
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data?.size) chunksRef.current.push(e.data); };
      rec.onstop = handleStop;
      rec.start();
      setPhase('recording');
      timerRef.current = setInterval(() => {
        setSeconds((s) => {
          const next = s + 1;
          if (next >= MAX_SECONDS) { try { rec.stop(); } catch { /* */ } }
          return next;
        });
      }, 1000);
    } catch (e) {
      toast.error('Microphone permission denied');
      cleanupRecorder();
      setOpen(false);
    }
  };

  const stopRecording = () => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      try { recorderRef.current.stop(); } catch { /* */ }
    }
  };

  const cancel = () => {
    try { recorderRef.current?.stop(); } catch { /* */ }
    cleanupRecorder();
    setPhase('idle');
    setOpen(false);
  };

  const handleStop = async () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    const chunks = chunksRef.current;
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch { /* */ }
    streamRef.current = null;
    if (!chunks.length) {
      setPhase('idle');
      setOpen(false);
      return;
    }
    setPhase('processing');
    const blob = new Blob(chunks, { type: chunks[0]?.type || 'audio/webm' });
    chunksRef.current = [];
    try {
      const fd = new FormData();
      fd.append('file', blob, 'voice.webm');
      const { data } = await api.post('/voice/expense', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setTranscript(data?.transcript || '');
      const items = data?.items?.length ? data.items : [{ name: data?.sub_category || 'Expense', quantity: 1, unit_price: data?.total_amount || 0 }];
      sessionStorage.setItem('bill4pe_draft', JSON.stringify({
        category: data?.category || 'other',
        sub_category: data?.sub_category || 'Misc',
        items,
        prefill_merchant: data?.merchant_name
          ? { merchant_name: data.merchant_name, merchant_upi: '', merchant_mobile: '' }
          : null,
        voice_transcript: data?.transcript || '',
      }));
      toast.success(`Heard: "${(data?.transcript || '').slice(0, 60)}"`);
      // brief delay so user sees the transcript
      setTimeout(() => {
        setOpen(false);
        setPhase('idle');
        nav('/app/editor');
      }, 900);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Voice processing failed');
      setOpen(false);
      setPhase('idle');
    }
  };

  return (
    <>
      <motion.button
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        whileHover={{ y: -2 }}
        onClick={startRecording}
        data-testid="voice-expense-btn"
        className="press-down relative w-full overflow-hidden rounded-2xl bg-navy text-white p-4 text-left group"
      >
        <div
          className="absolute inset-0 opacity-60 pointer-events-none"
          style={{
            background:
              'radial-gradient(circle at 85% 30%, rgba(212,255,0,0.18), transparent 55%),' +
              'radial-gradient(circle at 10% 90%, rgba(31,111,235,0.30), transparent 55%)',
          }}
        />
        <Mic className="absolute -right-4 -bottom-4 w-28 h-28 text-white/[0.06]" strokeWidth={1} />
        <div className="relative flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-lime text-navy grid place-items-center shrink-0 shadow-lg shadow-lime/20 pulse-brand">
            <Mic className="w-6 h-6" strokeWidth={2} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="inline-flex items-center gap-1 text-[9px] uppercase tracking-[0.25em] font-bold bg-lime text-navy px-1.5 py-0.5 rounded-full">
              <Sparkles className="w-2.5 h-2.5" /> Voice AI
            </div>
            <div className="font-display font-bold text-base mt-1 leading-tight">
              Speak to log expense
            </div>
            <div className="text-[11px] text-white/60 mt-0.5 leading-snug">
              <span className="text-lime">"Spent 250 on lunch"</span> — Hindi / English / Hinglish
            </div>
          </div>
        </div>
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[60] bg-black/85 backdrop-blur-sm grid place-items-center px-6"
            data-testid="voice-overlay"
          >
            <motion.div
              initial={{ scale: 0.9, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.9, y: 20 }}
              className="relative w-full max-w-sm rounded-3xl bg-navy text-white p-6 overflow-hidden"
            >
              <button
                onClick={cancel}
                className="absolute top-3 right-3 w-9 h-9 grid place-items-center bg-white/10 backdrop-blur rounded-full text-white"
                data-testid="voice-close-btn"
                disabled={phase === 'processing'}
              >
                <X className="w-4 h-4" />
              </button>

              {phase === 'recording' && (
                <div className="flex flex-col items-center text-center pt-2">
                  <div className="relative w-28 h-28 grid place-items-center">
                    <div className="absolute inset-0 rounded-full bg-red-500/30 animate-ping" />
                    <div className="absolute inset-2 rounded-full bg-red-500/40 animate-ping [animation-delay:0.4s]" />
                    <div className="relative w-20 h-20 rounded-full bg-red-500 grid place-items-center shadow-2xl shadow-red-500/40">
                      <Mic className="w-8 h-8 text-white" strokeWidth={2.5} />
                    </div>
                  </div>
                  <div className="mt-5 text-[10px] uppercase tracking-[0.3em] text-lime font-bold">
                    Listening...
                  </div>
                  <div className="font-mono text-2xl font-bold mt-2" data-testid="voice-timer">
                    0:{String(seconds).padStart(2, '0')} <span className="text-white/40 text-sm">/ 0:{MAX_SECONDS}</span>
                  </div>
                  <div className="text-xs text-white/60 mt-2 px-4 leading-snug">
                    Try: "Spent 250 on lunch at Saravana Bhavan"
                  </div>
                  <button
                    onClick={stopRecording}
                    data-testid="voice-stop-btn"
                    className="press-down mt-6 inline-flex items-center gap-2 h-11 px-6 bg-lime hover:bg-lime/90 text-navy rounded-full font-bold text-sm"
                  >
                    <Square className="w-4 h-4 fill-current" /> Stop & Process
                  </button>
                </div>
              )}

              {phase === 'processing' && (
                <div className="flex flex-col items-center text-center pt-3 pb-1">
                  <div className="relative w-24 h-24 grid place-items-center">
                    <div className="absolute inset-0 rounded-full border-2 border-brand/30" />
                    <Loader2 className="absolute inset-0 m-auto w-24 h-24 text-brand animate-spin" strokeWidth={1.5} />
                    <Mic className="relative w-9 h-9 text-lime" strokeWidth={2} />
                  </div>
                  <div className="mt-5 text-[10px] uppercase tracking-[0.3em] text-brand font-bold">
                    AI Processing...
                  </div>
                  <div className="text-sm font-semibold mt-2">
                    Whisper → Gemini → Draft
                  </div>
                  {transcript && (
                    <div className="mt-4 w-full px-3 py-2.5 rounded-xl bg-white/5 border border-white/10 text-xs text-white/80 italic">
                      "{transcript}"
                    </div>
                  )}
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

export default VoiceExpense;
