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
  const recognitionRef = useRef(null);
  const transcriptRef = useRef('');
  const finalTranscriptRef = useRef('');
  const cancelledRef = useRef(false);

  const stopRecognition = () => {
    try { recognitionRef.current?.stop?.(); } catch { /* browser may already have stopped */ }
    recognitionRef.current = null;
  };

  const cleanupRecorder = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    stopRecognition();
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch { /* */ }
    streamRef.current = null;
    recorderRef.current = null;
    chunksRef.current = [];
  };

  useEffect(() => () => cleanupRecorder(), []);

  // Browser speech recognition runs in PARALLEL with MediaRecorder on supported
  // web browsers. Gemini audio is still used, but this gives us a text fallback
  // when the audio codec/network/model fails and also lets the user see what was heard.
  const startBrowserSpeech = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;
    try {
      const recognition = new SpeechRecognition();
      recognition.lang = 'en-IN';
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      recognition.onresult = (event) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const text = event.results[i]?.[0]?.transcript || '';
          if (event.results[i].isFinal) finalTranscriptRef.current += `${text} `;
          else interim += `${text} `;
        }
        const heard = `${finalTranscriptRef.current}${interim}`.trim();
        transcriptRef.current = heard;
        setTranscript(heard);
      };
      recognition.onerror = () => { /* audio upload remains the primary fallback */ };
      recognitionRef.current = recognition;
      recognition.start();
    } catch { /* SpeechRecognition is optional */ }
  };

  const startRecording = async () => {
    setOpen(true);
    setTranscript('');
    transcriptRef.current = '';
    finalTranscriptRef.current = '';
    cancelledRef.current = false;
    setSeconds(0);

    if (typeof window !== 'undefined' && window.isSecureContext === false) {
      toast.error('Microphone needs a secure (HTTPS) connection. Open the site over https:// and try again.');
      setOpen(false);
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      toast.error('Voice recording not supported on this browser. Use latest Chrome/Safari over HTTPS.');
      setOpen(false);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const supported = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/mp4',
      ].find((m) => MediaRecorder.isTypeSupported?.(m));
      const opts = supported ? { mimeType: supported, audioBitsPerSecond: 32000 } : { audioBitsPerSecond: 32000 };
      let rec;
      try { rec = new MediaRecorder(stream, opts); } catch { rec = new MediaRecorder(stream); }
      recorderRef.current = rec;
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data?.size) chunksRef.current.push(e.data); };
      rec.onstop = handleStop;
      rec.start(500);
      startBrowserSpeech();
      setPhase('recording');
      timerRef.current = setInterval(() => {
        setSeconds((s) => {
          const next = s + 1;
          if (next >= MAX_SECONDS) {
            try { if (rec.state !== 'inactive') rec.stop(); } catch { /* */ }
          }
          return next;
        });
      }, 1000);
    } catch (e) {
      const name = e?.name || '';
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        toast.error('Microphone permission denied. Allow mic access in your browser and retry.');
      } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        toast.error('No microphone found on this device.');
      } else {
        toast.error('Could not start microphone. Please check mic access and try again.');
      }
      cleanupRecorder();
      setOpen(false);
    }
  };

  const stopRecording = () => {
    stopRecognition();
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      try { recorderRef.current.stop(); } catch { /* */ }
    }
  };

  const cancel = () => {
    cancelledRef.current = true;
    stopRecognition();
    const rec = recorderRef.current;
    if (rec && rec.state !== 'inactive') {
      rec.onstop = null;
      try { rec.stop(); } catch { /* */ }
    }
    cleanupRecorder();
    setPhase('idle');
    setOpen(false);
  };

  const saveDraftAndOpen = (data) => {
    const heard = data?.transcript || transcriptRef.current || '';
    const items = data?.items?.length
      ? data.items
      : (Number(data?.total_amount || 0) > 0
        ? [{ name: data?.sub_category || 'Expense', quantity: 1, unit_price: data?.total_amount || 0 }]
        : []);
    sessionStorage.setItem('bill4pe_draft', JSON.stringify({
      category: data?.category || 'other',
      sub_category: data?.sub_category || 'Misc',
      items,
      prefill_merchant: data?.merchant_name
        ? { merchant_name: data.merchant_name, merchant_upi: '', merchant_mobile: '' }
        : null,
      voice_transcript: heard,
    }));
    setTranscript(heard);
    toast.success(heard ? `Heard: "${heard.slice(0, 60)}"` : 'Voice expense captured');
    setTimeout(() => {
      setOpen(false);
      setPhase('idle');
      nav('/app/editor');
    }, 700);
  };

  const parseTextFallback = async (heard) => {
    if (!heard?.trim()) return null;
    const { data } = await api.post('/voice/expense-text', { transcript: heard.trim() });
    return data;
  };

  const handleStop = async () => {
    if (cancelledRef.current) return;
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    stopRecognition();
    const chunks = chunksRef.current;
    const heard = transcriptRef.current.trim();
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch { /* */ }
    streamRef.current = null;
    recorderRef.current = null;
    setPhase('processing');

    try {
      let data = null;
      if (chunks.length) {
        const mime = chunks[0]?.type || 'audio/webm';
        const ext = mime.includes('mp4') ? 'm4a' : (mime.includes('ogg') ? 'ogg' : 'webm');
        const blob = new Blob(chunks, { type: mime });
        const fd = new FormData();
        fd.append('file', blob, `voice.${ext}`);
        fd.append('transcript_hint', heard);
        try {
          const res = await api.post('/voice/expense', fd, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });
          data = res.data;
        } catch (audioErr) {
          // If the browser already heard the words, never throw that text away.
          if (!heard) throw audioErr;
          data = await parseTextFallback(heard);
        }
      } else if (heard) {
        data = await parseTextFallback(heard);
      }
      chunksRef.current = [];
      if (!data) throw new Error('No audio or speech text captured');
      saveDraftAndOpen(data);
    } catch (err) {
      chunksRef.current = [];
      toast.error(err?.response?.data?.detail || 'Could not understand the voice. Please speak the item and amount clearly.');
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
            <div className="font-display font-bold text-base mt-1 leading-tight">Speak to log expense</div>
            <div className="text-[11px] text-white/60 mt-0.5 leading-snug">
              <span className="text-lime">"Spent 250 on lunch"</span> — Hindi / English / Hinglish
            </div>
          </div>
        </div>
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[60] bg-black/85 backdrop-blur-sm grid place-items-center px-6"
            data-testid="voice-overlay"
          >
            <motion.div
              initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}
              className="relative w-full max-w-sm rounded-3xl bg-navy text-white p-6 overflow-hidden"
            >
              <button
                onClick={cancel}
                className="absolute top-3 right-3 w-9 h-9 grid place-items-center bg-white/10 backdrop-blur rounded-full text-white"
                data-testid="voice-close-btn" disabled={phase === 'processing'}
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
                  <div className="mt-5 text-[10px] uppercase tracking-[0.3em] text-lime font-bold">Listening...</div>
                  <div className="font-mono text-2xl font-bold mt-2" data-testid="voice-timer">
                    0:{String(seconds).padStart(2, '0')} <span className="text-white/40 text-sm">/ 0:{MAX_SECONDS}</span>
                  </div>
                  {transcript ? (
                    <div className="mt-3 w-full px-3 py-2.5 rounded-xl bg-white/5 border border-white/10 text-xs text-white/85" data-testid="voice-live-transcript">
                      {transcript}
                    </div>
                  ) : (
                    <div className="text-xs text-white/60 mt-2 px-4 leading-snug">Try: "Spent 250 on lunch at Saravana Bhavan"</div>
                  )}
                  <button
                    onClick={stopRecording} data-testid="voice-stop-btn"
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
                  <div className="mt-5 text-[10px] uppercase tracking-[0.3em] text-brand font-bold">AI Processing...</div>
                  <div className="text-sm font-semibold mt-2">Understanding your expense</div>
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
