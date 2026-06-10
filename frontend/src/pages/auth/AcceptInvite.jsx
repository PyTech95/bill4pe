import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { Building2, Lock, ArrowLeft, BadgeCheck } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import api from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { toast } from 'sonner';

export default function AcceptInvite() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const token = params.get('token') || '';
  const { refreshUser } = useAuth();

  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) { setError('Missing invite token'); return; }
    api.get(`/company/invite/${token}`)
      .then(({ data }) => setInfo(data))
      .catch((e) => setError(e?.response?.data?.detail || 'Invite is invalid or expired'));
  }, [token]);

  const accept = async (e) => {
    e.preventDefault();
    if (password.length < 6) { toast.error('Password must be 6+ characters'); return; }
    setBusy(true);
    try {
      const { data } = await api.post('/company/invite/accept', { token, password });
      localStorage.setItem('bill4pe_token', data.token);
      localStorage.setItem('bill4pe_user', JSON.stringify(data.user));
      await refreshUser();
      toast.success(`Welcome to ${info?.company_name || 'the team'}!`);
      nav('/app');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to accept invite');
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen bg-navy text-white grid md:grid-cols-2">
      <div className="hidden md:flex flex-col justify-between p-12">
        <Link to="/" className="self-start bg-white inline-flex items-center p-3 rounded-xl">
          <img src="/logo.png?v=5" alt="Bil4Pe" className="h-20 w-auto object-contain" />
        </Link>
        <div>
          <div className="font-display text-5xl font-bold leading-tight">
            You&apos;ve been invited.
          </div>
          <p className="text-white/60 mt-4 max-w-sm">
            Set your password to start submitting expenses for reimbursement.
          </p>
        </div>
        <div className="text-xs text-white/40">© 2026 BILL4PE</div>
      </div>

      <div className="flex items-center justify-center p-6 bg-white text-navy relative">
        <Link
          to="/"
          data-testid="invite-back-btn"
          className="press-down absolute top-4 left-4 inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-semibold text-slate-500 hover:text-navy hover:bg-slate-100"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back
        </Link>

        <form onSubmit={accept} className="w-full max-w-sm py-12" data-testid="invite-form">
          <div className="md:hidden bg-white inline-flex items-center p-2 rounded-xl mb-8">
            <img src="/logo.png?v=5" alt="Bil4Pe" className="h-14 w-auto object-contain" />
          </div>

          {error ? (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700" data-testid="invite-error">
              {error}
            </div>
          ) : !info ? (
            <div className="text-sm text-slate-400">Verifying invite...</div>
          ) : (
            <>
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.3em] text-brand font-bold">
                <BadgeCheck className="w-3.5 h-3.5" /> Verified invite
              </div>
              <h1 className="font-display font-bold text-3xl mt-1">Join {info.company_name}</h1>
              <p className="text-sm text-slate-500 mt-1">
                Hi <b className="text-navy">{info.name}</b> — set a password to activate your account.
              </p>

              <div className="mt-6 space-y-3">
                <div className="rounded-xl bg-slate-50 border border-soft p-3 text-xs text-slate-600 flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-navy" />
                  <span className="font-mono truncate">{info.email}</span>
                </div>
                <div className="relative">
                  <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <Input
                    required type="password" placeholder="Choose a password (6+ chars)"
                    value={password} onChange={(e) => setPassword(e.target.value)}
                    className="pl-10 h-12 rounded-xl border-soft"
                    data-testid="invite-password-input"
                  />
                </div>
                <Button
                  type="submit" disabled={busy}
                  className="press-down w-full h-12 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
                  data-testid="invite-submit-btn"
                >
                  {busy ? 'Activating...' : 'Accept & continue'}
                </Button>
              </div>
            </>
          )}
        </form>
      </div>
    </div>
  );
}
