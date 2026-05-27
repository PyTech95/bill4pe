import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ScanLine, QrCode, FileText, Wallet, Sparkles, ArrowRight, Check,
  Building2, ShieldCheck, Smartphone, Send,
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
            <Pill dark><Sparkles className="w-3 h-3" /> AI Powered Reimbursement</Pill>
            <h1 className="font-display font-bold text-4xl sm:text-5xl lg:text-7xl mt-6 tracking-tight leading-[1.05]">
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
                className="press-down inline-flex items-center gap-2 bg-lime text-navy font-semibold px-6 py-3.5 rounded-full hover:bg-[#BCE300]"
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
            <div className="relative mx-auto w-[280px] sm:w-[320px] rotate-[-3deg]">
              <div className="absolute -inset-6 rounded-[2.5rem] bg-lime/10 blur-2xl" />
              <div className="relative bg-[#0F1740] border border-white/10 rounded-[2.2rem] p-3 shadow-2xl">
                <div className="bg-white rounded-[1.8rem] overflow-hidden">
                  <div className="bg-navy px-5 pt-6 pb-10 text-white">
                    <div className="text-[10px] tracking-[0.3em] text-lime/80">WALLET BALANCE</div>
                    <div className="font-mono text-4xl mt-1.5">₹ 248.00</div>
                  </div>
                  <div className="-mt-6 px-4 space-y-2.5">
                    {[
                      { l: 'Roti', q: 3, p: 15 },
                      { l: 'Dal', q: 1, p: 50 },
                      { l: 'Rice', q: 1, p: 50 },
                      { l: 'Sabji', q: 1, p: 60 },
                    ].map((i) => (
                      <div key={i.l} className="bg-white border border-soft rounded-xl px-4 py-3 flex items-center justify-between">
                        <div>
                          <div className="text-sm font-semibold text-navy">{i.l}</div>
                          <div className="text-[10px] text-slate-400 font-mono">QTY × {i.q}</div>
                        </div>
                        <div className="font-mono text-sm text-navy">₹{i.p * i.q}</div>
                      </div>
                    ))}
                    <div className="px-4 py-3 bg-lime rounded-xl flex items-center justify-between">
                      <span className="text-xs font-bold tracking-wider text-navy">TOTAL</span>
                      <span className="font-mono font-bold text-navy">₹ 175.00</span>
                    </div>
                    <button className="w-full bg-navy text-white rounded-xl py-3 text-sm font-semibold mb-3">
                      Pay Now via UPI
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </Section>

      {/* trust strip */}
      <div className="border-t border-white/10 bg-black">
        <div className="overflow-hidden">
          <div className="marquee py-5 text-white/40 text-xs uppercase tracking-[0.4em] font-semibold">
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
  <Section className="py-24 bg-navy text-white">
    <div className="grid md:grid-cols-2 gap-12">
      <div>
        <Pill dark>Our Vision</Pill>
        <h3 className="font-display text-3xl sm:text-4xl font-bold mt-5 tracking-tight">
          Zero-friction expense reimbursement for every Indian professional.
        </h3>
      </div>
      <div>
        <Pill dark>Our Mission</Pill>
        <h3 className="font-display text-3xl sm:text-4xl font-bold mt-5 tracking-tight">
          Replace paper receipts and clunky forms with a single AI-first mobile workflow.
        </h3>
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
            className="press-down w-full h-12 bg-lime text-navy hover:bg-[#BCE300] rounded-full font-semibold"
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
        <div className="font-display font-bold text-5xl sm:text-7xl tracking-tighter">
          billforpay<span className="text-lime">.</span>com
        </div>
        <p className="mt-5 text-white/50 max-w-md">
          Pay Your Bill — AI Powered Expense & Invoice Platform.
          Made for India's professionals.
        </p>
      </div>
      <div className="md:col-span-2">
        <div className="text-xs uppercase tracking-wider text-white/40">Product</div>
        <ul className="mt-4 space-y-2 text-sm">
          <li><a href="#how" className="hover:text-lime">How it works</a></li>
          <li><Link to="/app" className="hover:text-lime">Launch app</Link></li>
        </ul>
      </div>
      <div className="md:col-span-3">
        <div className="text-xs uppercase tracking-wider text-white/40">Company</div>
        <ul className="mt-4 space-y-2 text-sm">
          <li><a href="#contact" className="hover:text-lime">Contact</a></li>
          <li><a className="hover:text-lime">Privacy</a></li>
          <li><a className="hover:text-lime">Terms</a></li>
        </ul>
      </div>
    </div>
    <div className="mt-14 pt-6 border-t border-white/10 flex justify-between text-xs text-white/40">
      <div>© 2026 BILL4PE</div>
      <div>Made in India</div>
    </div>
  </footer>
);

export default function Landing() {
  useEffect(() => { document.title = 'BILL4PE — AI Expense & Invoice Platform'; }, []);
  return (
    <div className="min-h-screen bg-white">
      <nav className="absolute top-0 left-0 right-0 z-40">
        <div className="px-5 md:px-10 lg:px-20 h-16 flex items-center justify-between text-white">
          <Link to="/" className="font-display font-bold text-lg tracking-tight">BILL4PE</Link>
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
  );
}
