import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ScanText, X, Loader2, Sparkles, Receipt } from 'lucide-react';
import { toast } from 'sonner';
import api from '@/lib/api';
import { catByKey } from '@/lib/categories';

export const ReceiptScan = () => {
  const nav = useNavigate();
  const fileRef = useRef(null);
  const [scanning, setScanning] = useState(false);
  const [preview, setPreview] = useState(null);

  const onPick = () => fileRef.current?.click();

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    setScanning(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post('/ai/scan-receipt', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const items = data?.items?.length
        ? data.items
        : (data?.total > 0 ? [{ name: data?.merchant_name || 'Receipt total', quantity: 1, unit_price: data.total }] : []);
      if (!items.length) {
        toast.warning('Could not read this receipt — try a clearer photo');
        return;
      }
      sessionStorage.setItem('bill4pe_draft', JSON.stringify({
        category: data?.category || 'other',
        sub_category: catByKey(data?.category)?.sub?.[0] || 'Misc',
        items,
        prefill_merchant: data?.merchant_name
          ? { merchant_name: data.merchant_name, merchant_upi: '', merchant_mobile: '' }
          : null,
        receipt_meta: { date: data?.date || '', subtotal: data?.subtotal || 0, tax: data?.tax || 0, total: data?.total || 0 },
      }));
      toast.success(`${items.length} items detected · ₹${(data?.total || 0).toFixed(0)}`);
      setTimeout(() => nav('/app/editor'), 600);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Receipt scan failed');
    } finally {
      setScanning(false);
      // input reset so same file can be picked again
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <>
      <motion.button
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        whileHover={{ y: -2 }}
        onClick={onPick}
        data-testid="receipt-scan-btn"
        className="press-down relative w-full overflow-hidden rounded-2xl bg-white border border-soft p-4 text-left group"
      >
        <Receipt className="absolute -right-4 -bottom-4 w-24 h-24 text-navy/[0.04]" strokeWidth={1} />
        <div className="relative flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-navy text-lime grid place-items-center shrink-0 shadow-md">
            <ScanText className="w-6 h-6" strokeWidth={2} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="inline-flex items-center gap-1 text-[9px] uppercase tracking-[0.25em] font-bold bg-navy text-lime px-1.5 py-0.5 rounded-full">
              <Sparkles className="w-2.5 h-2.5" /> Receipt OCR
            </div>
            <div className="font-display font-bold text-base text-navy mt-1 leading-tight">
              Scan printed bill
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5 leading-snug">
              Swiggy · BigBazaar · DMart · restaurant slips — auto-extract items
            </div>
          </div>
        </div>
      </motion.button>

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={onFile}
        data-testid="receipt-file-input"
      />

      <AnimatePresence>
        {scanning && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[60] bg-black/85 backdrop-blur-sm grid place-items-center px-6"
            data-testid="receipt-scan-overlay"
          >
            <div className="relative w-full max-w-sm aspect-[3/4] rounded-3xl overflow-hidden bg-black">
              {preview && <img src={preview} alt="receipt" className="absolute inset-0 w-full h-full object-cover opacity-70" />}
              <div className="scan-laser" />
              <div className="absolute inset-x-0 bottom-0 p-4 bg-gradient-to-t from-black/90 to-transparent text-white">
                <div className="flex items-center gap-2 text-lime text-xs uppercase tracking-wider font-bold">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Reading receipt with AI...
                </div>
                <div className="text-[11px] text-white/60 mt-1">Detecting merchant, items & total</div>
              </div>
              <button
                onClick={() => setScanning(false)}
                className="absolute top-3 right-3 w-9 h-9 grid place-items-center bg-white/10 backdrop-blur rounded-full text-white"
                data-testid="receipt-scan-close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

export default ReceiptScan;
