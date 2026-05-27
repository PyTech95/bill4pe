import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Gift, Copy, Share2, Users, IndianRupee, Sparkles, Check, ArrowRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import api from '@/lib/api';

export default function Referrals() {
  const [data, setData] = useState({ code: '', total_referrals: 0, total_earnings: 0, referrals: [], bonus_per_referral: 50 });
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api.get('/referrals/me').then((r) => setData(r.data)).catch(() => {});
  }, []);

  const inviteLink = () => `${window.location.origin}/register?ref=${data.code}`;
  const phoneInviteLink = () => `${window.location.origin}/login/phone?ref=${data.code}`;

  const message = () =>
    `Hey! I'm using BILL4PE — an AI-powered expense and reimbursement app. ` +
    `Sign up with my code ${data.code} and we both get ₹${data.bonus_per_referral} wallet credit. ` +
    `${inviteLink()}`;

  const copyCode = async () => {
    await navigator.clipboard?.writeText(data.code);
    setCopied(true);
    toast.success(`Code ${data.code} copied`);
    setTimeout(() => setCopied(false), 1800);
  };

  const copyLink = async () => {
    await navigator.clipboard?.writeText(inviteLink());
    toast.success('Invite link copied');
  };

  const share = async () => {
    const text = message();
    if (navigator.share) {
      try { await navigator.share({ title: 'Join me on BILL4PE', text }); } catch { /* cancelled */ }
    } else {
      await navigator.clipboard?.writeText(text);
      toast.success('Invite message copied');
    }
  };

  const whatsapp = () => {
    const url = `https://wa.me/?text=${encodeURIComponent(message())}`;
    window.open(url, '_blank', 'noopener');
  };

  return (
    <div className="space-y-6 pb-6">
      <div>
        <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Refer & earn</div>
        <h1 className="font-display text-2xl font-bold text-navy mt-1">Invite friends, earn ₹{data.bonus_per_referral}</h1>
        <p className="text-sm text-slate-500 mt-1">
          You get <span className="font-semibold text-navy">₹{data.bonus_per_referral}</span>, your friend gets{' '}
          <span className="font-semibold text-navy">₹{data.bonus_per_referral}</span> when they sign up.
        </p>
      </div>

      {/* Hero referral card */}
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-3xl bg-navy text-white p-6"
      >
        <div
          className="absolute inset-0 opacity-60 pointer-events-none"
          style={{
            background:
              'radial-gradient(circle at 85% 15%, rgba(31,111,235,0.40), transparent 50%),' +
              'radial-gradient(circle at 10% 90%, rgba(212,255,0,0.10), transparent 50%)',
          }}
        />
        <div className="absolute -right-6 -bottom-6 w-44 h-44 text-white/[0.05]">
          <Gift className="w-full h-full" strokeWidth={1} />
        </div>

        <div className="relative">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-[0.25em] bg-brand/15 text-brand border border-brand/20">
            <Sparkles className="w-3 h-3" /> Your code
          </div>
          <div className="font-mono text-5xl font-bold mt-4 tracking-widest" data-testid="referral-code">
            {data.code || '— — — —'}
          </div>

          <div className="mt-6 flex gap-2">
            <button
              onClick={copyCode}
              data-testid="referral-copy-code-btn"
              className="press-down flex-1 inline-flex items-center justify-center gap-1.5 h-11 rounded-full bg-white text-navy text-sm font-semibold hover:bg-white/90"
            >
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              {copied ? 'Copied' : 'Copy code'}
            </button>
            <button
              onClick={copyLink}
              data-testid="referral-copy-link-btn"
              className="press-down h-11 px-4 rounded-full border border-white/20 text-white text-sm font-semibold hover:bg-white/10"
            >
              Copy link
            </button>
          </div>
        </div>
      </motion.div>

      {/* Share actions */}
      <div className="grid grid-cols-2 gap-3">
        <button
          onClick={whatsapp}
          data-testid="referral-whatsapp-btn"
          className="press-down flat-card p-4 text-left hover:border-navy flex items-center gap-3"
        >
          <div className="w-10 h-10 rounded-xl bg-[#25D366] text-white grid place-items-center">
            <Share2 className="w-5 h-5" />
          </div>
          <div className="flex-1">
            <div className="font-display font-bold text-sm text-navy">WhatsApp</div>
            <div className="text-[10px] text-slate-400 mt-0.5">Share with contacts</div>
          </div>
        </button>
        <button
          onClick={share}
          data-testid="referral-share-btn"
          className="press-down flat-card p-4 text-left hover:border-navy flex items-center gap-3"
        >
          <div className="w-10 h-10 rounded-xl bg-brand text-white grid place-items-center">
            <Share2 className="w-5 h-5" />
          </div>
          <div className="flex-1">
            <div className="font-display font-bold text-sm text-navy">More apps</div>
            <div className="text-[10px] text-slate-400 mt-0.5">Native share sheet</div>
          </div>
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3">
        <div className="flat-card p-4">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-400 font-bold">
            <Users className="w-3 h-3" /> Friends joined
          </div>
          <div className="font-mono text-2xl font-bold text-navy mt-2" data-testid="referral-count">
            {data.total_referrals}
          </div>
        </div>
        <div className="flat-card p-4">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-400 font-bold">
            <IndianRupee className="w-3 h-3" /> Total earned
          </div>
          <div className="font-mono text-2xl font-bold text-brand mt-2" data-testid="referral-earnings">
            ₹{data.total_earnings.toFixed(0)}
          </div>
        </div>
      </div>

      {/* How it works */}
      <div className="flat-card p-5">
        <div className="text-xs uppercase tracking-wider text-slate-400 font-bold">How it works</div>
        <div className="mt-4 space-y-3.5">
          {[
            { n: 1, t: 'Share your code', d: 'Send via WhatsApp, message or copy link.' },
            { n: 2, t: 'Friend signs up', d: 'They enter your code on the signup screen.' },
            { n: 3, t: 'Both get ₹50', d: 'Wallet credited instantly when they join.' },
          ].map((s, i) => (
            <div key={s.n} className="flex items-start gap-3">
              <div className="w-7 h-7 rounded-full bg-brand text-white font-bold text-sm grid place-items-center shrink-0 mt-0.5">
                {s.n}
              </div>
              <div>
                <div className="font-semibold text-navy text-sm">{s.t}</div>
                <div className="text-xs text-slate-500 mt-0.5">{s.d}</div>
              </div>
              {i < 2 && <ArrowRight className="w-4 h-4 text-slate-300 ml-auto mt-2 hidden sm:block" />}
            </div>
          ))}
        </div>
      </div>

      {/* Referred friends list */}
      {data.referrals.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-bold">Friends you've referred</div>
          <div className="mt-3 space-y-2">
            {data.referrals.map((r) => (
              <div key={r.id} className="flat-card p-3 flex items-center gap-3" data-testid={`referral-row-${r.id}`}>
                <div className="w-9 h-9 rounded-full bg-navy text-brand font-display font-bold text-sm grid place-items-center">
                  {(r.referee_name || 'F')[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-navy truncate">{r.referee_name}</div>
                  <div className="text-[10px] text-slate-400 font-mono">{r.joined_at?.slice(0, 10)}</div>
                </div>
                <div className="font-mono font-bold text-brand text-sm">+ ₹{r.bonus.toFixed(0)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-center text-[10px] text-slate-400 pt-4">
        Bonus credited automatically. Cannot be withdrawn — use it for bill generation & platform charges.
      </div>
    </div>
  );
}
