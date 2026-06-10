import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mail, Lock, ArrowLeft } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth';
import { toast } from 'sonner';

export default function Login() {
  const nav = useNavigate();
  const { login } = useAuth();
  const [form, setForm] = useState({ email: '', password: '' });
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(form.email, form.password);
      toast.success('Welcome back!');
      nav('/app');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Login failed');
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-navy text-white grid md:grid-cols-2">
      <div className="hidden md:flex flex-col justify-between p-12">
        <Link to="/" className="self-start bg-white inline-flex items-center p-3 rounded-xl">
          <img src="/logo.png?v=5" alt="Bil4Pe — The Intelligent Billing" className="h-20 w-auto object-contain" />
        </Link>
        <div>
          <div className="font-display text-5xl font-bold leading-tight">Welcome back.</div>
          <p className="text-white/60 mt-4 max-w-sm">Resume your AI-powered reimbursement workflow.</p>
        </div>
        <div className="text-xs text-white/40">© 2026 BILL4PE · www.bill4pe.com</div>
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
          <Link to="/" className="md:hidden mb-10 bg-white inline-flex items-center p-2 rounded-xl">
            <img src="/logo.png?v=5" alt="Bil4Pe — The Intelligent Billing" className="h-16 w-auto object-contain" />
          </Link>
          <h1 className="font-display font-bold text-3xl">Sign in</h1>
          <p className="text-sm text-slate-500 mt-1">Use your registered email and password.</p>

          <div className="mt-8 space-y-5">
            <div className="relative">
              <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                required type="email" placeholder="you@work.com"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="pl-10 h-12 rounded-xl border-soft"
                data-testid="login-email-input"
              />
            </div>
            <div className="relative">
              <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                required type="password" placeholder="••••••••"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="pl-10 h-12 rounded-xl border-soft"
                data-testid="login-password-input"
              />
            </div>
            <Button
              type="submit" disabled={loading}
              className="press-down w-full h-12 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
              data-testid="login-submit-btn"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </Button>
          </div>

          <div className="mt-6 text-sm text-slate-500 text-center space-y-2">
            <div>
              <Link to="/login/phone" className="text-navy font-semibold underline" data-testid="link-phone-login">
                Sign in with phone instead
              </Link>
            </div>
            <div>
              New here?{' '}
              <Link to="/register" className="text-navy font-semibold underline" data-testid="link-register">
                Create an account
              </Link>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
