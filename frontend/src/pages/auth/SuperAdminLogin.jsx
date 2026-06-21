import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mail, Lock, ArrowLeft, ShieldCheck } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth';
import { toast } from 'sonner';

export default function SuperAdminLogin() {
  const nav = useNavigate();
  const { login } = useAuth();
  const [form, setForm] = useState({ email: '', password: '' });
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const u = await login(form.email, form.password);
      if (!u?.is_super_admin) {
        toast.error('This account is not a super admin');
        return;
      }
      toast.success('Welcome, Super Admin');
      nav('/superadmin');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Login failed');
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-navy text-white grid md:grid-cols-2" data-testid="superadmin-login">
      <div className="hidden md:flex flex-col justify-between p-12 relative overflow-hidden">
        <div
          className="absolute inset-0 opacity-40 pointer-events-none"
          style={{
            background:
              'radial-gradient(circle at 20% 15%, rgba(212,255,0,0.18), transparent 45%), radial-gradient(circle at 85% 80%, rgba(24,88,204,0.25), transparent 50%)',
          }}
        />
        <Link to="/" className="relative self-start bg-white inline-flex items-center p-3 rounded-xl">
          <img src="/logo.png?v=6" alt="Bil4Pe" className="h-20 w-auto object-contain" />
        </Link>
        <div className="relative">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-brand/20 border border-brand/40 text-xs uppercase tracking-[0.2em] font-semibold mb-5">
            <ShieldCheck className="w-3.5 h-3.5" /> Platform Control
          </div>
          <div className="font-display text-5xl font-bold leading-tight">Super Admin Console</div>
          <p className="text-white/60 mt-4 max-w-sm">
            Manage users, companies, subscriptions and platform revenue across the entire Bill4Pe network.
          </p>
        </div>
        <div className="relative text-xs text-white/40">© 2026 BILL4PE · www.bill4pe.com</div>
      </div>

      <div className="flex items-center justify-center p-6 bg-white text-navy relative">
        <Link
          to="/"
          data-testid="superadmin-back-link"
          className="press-down absolute top-4 left-4 inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-semibold text-slate-500 hover:text-navy hover:bg-slate-100"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to home
        </Link>
        <form onSubmit={submit} className="w-full max-w-sm">
          <div className="md:hidden mb-8 inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-navy text-white">
            <ShieldCheck className="w-7 h-7" />
          </div>
          <h1 className="font-display font-bold text-3xl">Super Admin</h1>
          <p className="text-sm text-slate-500 mt-1">Restricted access. Authorized personnel only.</p>

          <div className="mt-8 space-y-5">
            <div className="relative">
              <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                required type="email" placeholder="admin@bill4pe.com"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="pl-10 h-12 rounded-xl border-soft"
                data-testid="superadmin-email-input"
              />
            </div>
            <div className="relative">
              <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                required type="password" placeholder="••••••••"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="pl-10 h-12 rounded-xl border-soft"
                data-testid="superadmin-password-input"
              />
            </div>
            <Button
              type="submit" disabled={loading}
              className="press-down w-full h-12 bg-navy text-white hover:bg-[#001a44] rounded-full font-semibold"
              data-testid="superadmin-submit-btn"
            >
              {loading ? 'Authenticating...' : 'Sign in to console'}
            </Button>
          </div>

          <div className="mt-8 text-xs text-slate-400 text-center">
            Not a super admin?{' '}
            <Link to="/login" className="text-navy font-semibold underline" data-testid="superadmin-back-to-user-login">
              Regular user sign in
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
