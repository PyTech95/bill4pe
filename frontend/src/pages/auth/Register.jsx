import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mail, Lock, User, ArrowLeft } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth';
import { toast } from 'sonner';

export default function Register() {
  const nav = useNavigate();
  const { register } = useAuth();
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (form.password.length < 6) { toast.error('Password must be 6+ chars'); return; }
    setLoading(true);
    try {
      await register(form.email, form.password, form.name);
      toast.success('Welcome to BILL4PE! ₹50 welcome bonus added.');
      nav('/app');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Registration failed');
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-navy text-white grid md:grid-cols-2">
      <div className="hidden md:flex flex-col justify-between p-12">
        <Link to="/" className="self-start bg-white inline-flex p-2 rounded-xl">
          <img src="/logo.png" alt="Bill4Pe" className="h-10 w-auto" />
        </Link>
        <div>
          <div className="font-display text-5xl font-bold leading-tight">Start in 30 seconds.</div>
          <p className="text-white/60 mt-4 max-w-sm">Get ₹50 welcome credit. Generate your first AI invoice today.</p>
        </div>
        <div className="text-xs text-white/40">© 2026 BILL4PE · billforpay.com</div>
      </div>

      <div className="flex items-center justify-center p-6 bg-white text-navy relative">
        <Link
          to="/"
          data-testid="back-to-landing-btn"
          className="press-down absolute top-4 left-4 inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-semibold text-slate-500 hover:text-navy hover:bg-slate-100"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to home
        </Link>
        <form onSubmit={submit} className="w-full max-w-sm">
          <Link to="/" className="md:hidden block mb-10 bg-white inline-flex p-2 rounded-xl">
            <img src="/logo.png" alt="Bill4Pe" className="h-10 w-auto" />
          </Link>
          <h1 className="font-display font-bold text-3xl">Create account</h1>
          <p className="text-sm text-slate-500 mt-1">Free forever. ₹5 only per generated invoice.</p>

          <div className="mt-8 space-y-5">
            <div className="relative">
              <User className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                required placeholder="Full name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="pl-10 h-12 rounded-xl border-soft"
                data-testid="register-name-input"
              />
            </div>
            <div className="relative">
              <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                required type="email" placeholder="you@work.com"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="pl-10 h-12 rounded-xl border-soft"
                data-testid="register-email-input"
              />
            </div>
            <div className="relative">
              <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                required type="password" placeholder="Min 6 characters"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="pl-10 h-12 rounded-xl border-soft"
                data-testid="register-password-input"
              />
            </div>
            <Button
              type="submit" disabled={loading}
              className="press-down w-full h-12 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
              data-testid="register-submit-btn"
            >
              {loading ? 'Creating account...' : 'Create account & get ₹50'}
            </Button>
          </div>

          <div className="mt-6 text-sm text-slate-500 text-center space-y-2">
            <div>
              <Link to="/login/phone" className="text-navy font-semibold underline" data-testid="link-phone-register">
                Continue with phone instead
              </Link>
            </div>
            <div>
              Already have an account?{' '}
              <Link to="/login" className="text-navy font-semibold underline" data-testid="link-login">
                Sign in
              </Link>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
