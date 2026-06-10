import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, MapPin, Phone, Mail, Send, Building2, Clock } from 'lucide-react';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import api from '@/lib/api';

const CONTACT_DETAILS = {
  name: 'Ujjwal Gupta',
  addressLine1: 'Plot No. 239, Second Floor, Saraswati Lane',
  addressLine2: 'Sector - 5, Vaishali',
  city: 'Ghaziabad, Uttar Pradesh - 201010',
  mobile: '+91 70111 84609',
  mobileRaw: '7011184609',
  email: 'support@bill4pe.com',
  hours: 'Mon – Sat, 10:00 AM – 7:00 PM IST',
};

const InfoTile = ({ icon: Icon, label, children, testId }) => (
  <div className="bg-white/[0.04] border border-white/10 rounded-2xl p-6 hover:border-brand transition-colors" data-testid={testId}>
    <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-lime/15 text-lime">
      <Icon className="w-5 h-5" strokeWidth={1.8} />
    </div>
    <div className="mt-4 text-[10px] uppercase tracking-[0.25em] font-bold text-white/50">
      {label}
    </div>
    <div className="mt-2 text-white leading-relaxed text-[14px]">
      {children}
    </div>
  </div>
);

export default function Contact() {
  useEffect(() => { document.title = 'Contact us · BILL4PE'; }, []);
  const [form, setForm] = useState({ name: '', email: '', message: '' });
  const [sending, setSending] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSending(true);
    try {
      await api.post('/contact', form);
      toast.success('Message sent. We will get back to you within one business day.');
      setForm({ name: '', email: '', message: '' });
    } catch {
      toast.error('Could not send right now. Please try again.');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-screen bg-navy text-white flex flex-col relative overflow-hidden">
      {/* ambient glow */}
      <div
        className="absolute inset-0 opacity-30 pointer-events-none"
        style={{
          background:
            'radial-gradient(circle at 20% 15%, rgba(212,255,0,0.18), transparent 45%), radial-gradient(circle at 85% 70%, rgba(24,88,204,0.22), transparent 50%)',
        }}
      />

      {/* top bar */}
      <header className="relative border-b border-white/10">
        <div className="max-w-5xl mx-auto px-5 md:px-8 h-16 flex items-center justify-between">
          <Link to="/" className="bg-white inline-flex items-center p-1.5 rounded-lg" data-testid="contact-nav-logo">
            <img src="/logo.png?v=5" alt="Bil4Pe — The Intelligent Billing" className="h-12 w-auto object-contain" />
          </Link>
          <Link
            to="/"
            data-testid="contact-back-btn"
            className="press-down inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-semibold text-white/70 hover:text-lime hover:bg-white/5"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back to home
          </Link>
        </div>
      </header>

      {/* hero */}
      <section className="relative px-5 md:px-8 pt-14 md:pt-20 pb-10">
        <div className="max-w-5xl mx-auto">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-[0.3em] text-lime bg-lime/10 border border-lime/20">
            Get in touch
          </div>
          <h1 className="font-display font-bold text-4xl sm:text-5xl lg:text-6xl mt-5 tracking-tight leading-[1.05]">
            Talk to the <span className="text-lime">BILL4PE</span> team.
          </h1>
          <p className="mt-5 max-w-2xl text-white/65 leading-relaxed text-[15px]">
            Partnerships, enterprise plans, refunds, support — we'd love to hear from you.
            Reach us using the details below or drop a message and we'll respond within one
            business day.
          </p>
        </div>
      </section>

      {/* main content */}
      <main className="relative flex-1 px-5 md:px-8 pb-16">
        <div className="max-w-5xl mx-auto grid md:grid-cols-12 gap-6">
          {/* left — contact info */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="md:col-span-5 space-y-4"
          >
            <InfoTile icon={Building2} label="Registered office" testId="contact-address-tile">
              <div className="font-semibold text-[15px]">{CONTACT_DETAILS.name}</div>
              <div className="mt-1.5 text-white/70 text-[13.5px] leading-[1.7]">
                {CONTACT_DETAILS.addressLine1}<br />
                {CONTACT_DETAILS.addressLine2}<br />
                {CONTACT_DETAILS.city}
              </div>
            </InfoTile>

            <InfoTile icon={Phone} label="Call / WhatsApp" testId="contact-phone-tile">
              <a
                href={`tel:${CONTACT_DETAILS.mobileRaw}`}
                className="font-mono text-lime hover:underline"
                data-testid="contact-phone-link"
              >
                {CONTACT_DETAILS.mobile}
              </a>
            </InfoTile>

            <InfoTile icon={Mail} label="Email" testId="contact-email-tile">
              <a
                href={`mailto:${CONTACT_DETAILS.email}`}
                className="text-lime hover:underline break-all"
                data-testid="contact-email-link"
              >
                {CONTACT_DETAILS.email}
              </a>
            </InfoTile>

            <InfoTile icon={Clock} label="Business hours" testId="contact-hours-tile">
              {CONTACT_DETAILS.hours}
            </InfoTile>

            <InfoTile icon={MapPin} label="Jurisdiction" testId="contact-jurisdiction-tile">
              Ghaziabad, Uttar Pradesh - 201010, India
            </InfoTile>
          </motion.div>

          {/* right — form */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="md:col-span-7"
          >
            <form
              onSubmit={submit}
              className="bg-white text-navy rounded-3xl p-7 md:p-9 shadow-2xl"
              data-testid="contact-form"
            >
              <div className="text-[11px] uppercase tracking-[0.3em] font-bold text-slate-400">
                Send us a message
              </div>
              <h2 className="font-display font-bold text-2xl sm:text-3xl mt-2 tracking-tight">
                We respond within 24 hours.
              </h2>

              <div className="mt-7 space-y-5">
                <div>
                  <label className="text-xs uppercase font-semibold tracking-wider text-slate-500">
                    Your name
                  </label>
                  <Input
                    required
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="e.g. Priya Sharma"
                    className="mt-2 h-12 rounded-xl"
                    data-testid="contact-name-input"
                  />
                </div>

                <div>
                  <label className="text-xs uppercase font-semibold tracking-wider text-slate-500">
                    Email
                  </label>
                  <Input
                    required
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    placeholder="you@company.com"
                    className="mt-2 h-12 rounded-xl"
                    data-testid="contact-email-input"
                  />
                </div>

                <div>
                  <label className="text-xs uppercase font-semibold tracking-wider text-slate-500">
                    Message
                  </label>
                  <Textarea
                    required
                    rows={5}
                    value={form.message}
                    onChange={(e) => setForm({ ...form, message: e.target.value })}
                    placeholder="How can we help?"
                    className="mt-2 rounded-xl"
                    data-testid="contact-message-input"
                  />
                </div>

                <Button
                  type="submit"
                  disabled={sending}
                  className="press-down w-full h-12 bg-navy text-lime hover:bg-[#11214a] rounded-full font-bold"
                  data-testid="contact-submit-btn"
                >
                  <Send className="w-4 h-4 mr-2" />
                  {sending ? 'Sending…' : 'Send message'}
                </Button>

                <p className="text-[11px] text-slate-400 text-center">
                  By submitting, you agree to our{' '}
                  <Link to="/terms" className="underline hover:text-brand">Terms</Link>{' '}&{' '}
                  <Link to="/privacy" className="underline hover:text-brand">Privacy</Link>.
                </p>
              </div>
            </form>
          </motion.div>
        </div>
      </main>

      {/* footer */}
      <footer className="relative bg-black/40 border-t border-white/10 px-5 md:px-8 py-8">
        <div className="max-w-5xl mx-auto flex flex-wrap items-center justify-between gap-4 text-sm">
          <div className="text-white/40">© 2026 BILL4PE · www.bill4pe.com</div>
          <div className="flex gap-5 text-white/60">
            <Link to="/privacy" className="hover:text-lime">Privacy</Link>
            <Link to="/terms" className="hover:text-lime">Terms</Link>
            <Link to="/contact" className="hover:text-lime">Contact</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
