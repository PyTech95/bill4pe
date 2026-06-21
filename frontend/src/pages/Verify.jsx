import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { CheckCircle2, XCircle, ShieldCheck, Receipt, Calendar, IndianRupee, Building2, ArrowRight } from 'lucide-react';
import { API } from '@/lib/api';

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-IN', {
      dateStyle: 'medium', timeStyle: 'short',
    });
  } catch { return iso; }
}

function Row({ icon: Icon, label, value, big }) {
  return (
    <div className="flex items-start gap-3 py-3 border-b border-white/5 last:border-0">
      <div className="mt-0.5 w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center text-lime-400 shrink-0">
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[11px] uppercase tracking-wider text-white/40 font-semibold">{label}</div>
        <div className={`mt-0.5 ${big ? 'text-2xl font-display font-bold' : 'text-sm'} text-white break-words`}>
          {value || <span className="text-white/40">—</span>}
        </div>
      </div>
    </div>
  );
}

export default function Verify() {
  const { billId } = useParams();
  const [state, setState] = useState({ loading: true, data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API}/public/verify/${encodeURIComponent(billId)}`);
        const json = await res.json();
        if (!cancelled) setState({ loading: false, data: json, error: null });
      } catch (e) {
        if (!cancelled) setState({ loading: false, data: null, error: 'Network error' });
      }
    })();
    return () => { cancelled = true; };
  }, [billId]);

  const { loading, data, error } = state;
  const valid = !!data?.valid;

  return (
    <div className="min-h-screen bg-[#0a0f1f] text-white relative overflow-hidden" data-testid="verify-page">
      {/* grain + glow */}
      <div className="pointer-events-none absolute inset-0 opacity-[0.07]" style={{
        backgroundImage: "radial-gradient(circle at 20% 10%, rgba(132,204,22,0.35), transparent 40%), radial-gradient(circle at 80% 90%, rgba(56,189,248,0.25), transparent 45%)",
      }} />

      <div className="max-w-xl mx-auto px-5 pt-12 pb-24 relative">
        {/* Header */}
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-white/60 hover:text-white" data-testid="verify-back-home">
          <span className="w-7 h-7 rounded-lg bg-lime-400 text-[#0a0f1f] grid place-items-center font-black">₹</span>
          <span className="font-display font-bold">BILL4PE</span>
        </Link>

        <motion.h1
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
          className="mt-8 font-display font-bold text-3xl sm:text-4xl leading-tight"
        >
          Bill verification
        </motion.h1>
        <p className="mt-2 text-sm text-white/60">
          Authenticity check for a BILL4PE-issued invoice.
        </p>

        {/* Status pill */}
        <motion.div
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
          className={`mt-6 rounded-2xl p-5 border ${valid ? 'border-lime-400/40 bg-lime-400/[0.06]' : 'border-rose-500/30 bg-rose-500/[0.05]'}`}
          data-testid={valid ? 'verify-status-valid' : 'verify-status-invalid'}
        >
          <div className="flex items-center gap-3">
            {loading ? (
              <div className="w-10 h-10 rounded-full bg-white/5 animate-pulse" />
            ) : valid ? (
              <CheckCircle2 className="w-10 h-10 text-lime-400" />
            ) : (
              <XCircle className="w-10 h-10 text-rose-400" />
            )}
            <div className="flex-1 min-w-0">
              <div className="text-lg font-display font-bold">
                {loading ? 'Checking…' : valid ? 'Verified ✓ Authentic bill' : 'Not a valid BILL4PE bill'}
              </div>
              <div className="text-xs text-white/55 mt-0.5 break-all">
                Bill ID: <span className="font-mono text-white/80">{billId}</span>
              </div>
            </div>
          </div>
          {!loading && !valid && (
            <div className="mt-3 text-sm text-white/70">
              {error
                ? 'Unable to reach BILL4PE servers. Please try again in a moment.'
                : 'No bill exists in our records with this ID. It may have been mistyped, tampered, or never issued by BILL4PE.'}
            </div>
          )}
        </motion.div>

        {/* Details */}
        {valid && (
          <motion.div
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            className="mt-5 rounded-2xl border border-white/10 bg-white/[0.03] p-5"
            data-testid="verify-details"
          >
            <Row icon={IndianRupee} label="Grand Total" value={`₹ ${(data.grand_total ?? data.amount ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} big />
            <Row icon={Building2} label="Merchant" value={data.merchant_name} />
            <Row icon={Receipt} label="Category" value={[data.category, data.sub_category].filter(Boolean).join(' · ')} />
            <Row icon={Calendar} label="Issued" value={fmtDate(data.issued_at)} />
            <Row icon={ShieldCheck} label="Issued to" value={data.customer_name ? `${data.customer_name} · BILL4PE user` : 'BILL4PE user'} />
            {data.fee != null && (
              <div className="mt-3 text-[11px] text-white/40">
                Includes BILL4PE convenience fee of ₹{Number(data.fee).toFixed(2)} (1% of bill, min ₹1).
              </div>
            )}
          </motion.div>
        )}

        {/* Footer CTA */}
        <div className="mt-8 text-sm text-white/55">
          BILL4PE bills come with a QR code on every PDF — scan it any time to confirm the bill is authentic and was generated through our platform.
        </div>
        <Link to="/" className="mt-4 inline-flex items-center gap-2 text-lime-400 hover:text-lime-300 font-semibold text-sm" data-testid="verify-cta-home">
          Visit BILL4PE <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
}
