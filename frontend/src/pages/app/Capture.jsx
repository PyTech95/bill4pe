import React, { useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Camera, PenLine, Loader2, ImagePlus } from 'lucide-react';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import api from '@/lib/api';
import { catByKey } from '@/lib/categories';

export default function Capture() {
  const { cat, sub } = useParams();
  const nav = useNavigate();
  const c = catByKey(cat);
  const fileRef = useRef(null);
  const [scanning, setScanning] = useState(false);
  const [preview, setPreview] = useState(null);

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    setScanning(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post(`/ai/detect-items?category=${encodeURIComponent(cat)}`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const items = data?.items || [];
      if (!items.length) {
        toast.warning('Could not detect items. Try a clearer photo or use manual entry.');
        setScanning(false);
        return;
      }
      sessionStorage.setItem('bill4pe_draft', JSON.stringify({
        category: cat, sub_category: sub, items,
      }));
      nav('/app/editor');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'AI detection failed');
      setScanning(false);
    }
  };

  const goManual = () => {
    sessionStorage.setItem('bill4pe_draft', JSON.stringify({
      category: cat, sub_category: sub, items: [{ name: '', quantity: 1, unit_price: 0 }],
    }));
    nav('/app/editor');
  };

  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">
          {c?.label} / {sub}
        </div>
        <h1 className="font-display text-2xl font-bold text-navy mt-1">Add your expense</h1>
      </div>

      {scanning && preview && (
        <div className="relative aspect-square rounded-2xl overflow-hidden bg-black">
          <img src={preview} alt="captured" className="absolute inset-0 w-full h-full object-cover opacity-70" />
          <div className="scan-laser" />
          <div className="absolute inset-x-0 bottom-0 p-4 bg-gradient-to-t from-black/80 to-transparent">
            <div className="flex items-center gap-2 text-lime">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-xs uppercase tracking-wider font-semibold">AI is detecting items...</span>
            </div>
          </div>
        </div>
      )}

      {!scanning && (
        <motion.div
          initial="hidden" animate="show"
          variants={{ show: { transition: { staggerChildren: 0.06 } } }}
          className="space-y-3"
        >
          <motion.button
            variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
            onClick={() => fileRef.current?.click()}
            data-testid="capture-take-image-btn"
            className="press-down w-full flat-card p-5 text-left hover:border-navy flex items-center gap-4"
          >
            <div className="w-12 h-12 rounded-xl bg-lime text-navy grid place-items-center">
              <Camera className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <div className="font-display font-bold text-navy">Take {c?.label} Image</div>
              <div className="text-xs text-slate-500 mt-0.5">AI auto-detects items, quantity & price</div>
            </div>
            <ImagePlus className="w-5 h-5 text-slate-300" />
          </motion.button>

          <motion.button
            variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
            onClick={goManual}
            data-testid="capture-manual-btn"
            className="press-down w-full flat-card p-5 text-left hover:border-navy flex items-center gap-4"
          >
            <div className="w-12 h-12 rounded-xl bg-navy text-white grid place-items-center">
              <PenLine className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <div className="font-display font-bold text-navy">Manual Entry</div>
              <div className="text-xs text-slate-500 mt-0.5">Type items with AI suggestions</div>
            </div>
          </motion.button>
        </motion.div>
      )}

      <input
        ref={fileRef} type="file" accept="image/*" capture="environment"
        className="hidden" onChange={onFile} data-testid="capture-file-input"
      />
    </div>
  );
}
