import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { BadgeCheck, Building2, KeyRound, Loader2, ArrowLeft } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import api from '@/lib/api';

export default function EmployeeLogin() {
  const [code, setCode] = useState('');
  const [pin, setPin] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!/^\d{6}$/.test(code) || !/^\d{6}$/.test(pin)) {
      toast.error('Enter your 6-digit employee code and 6-digit PIN');
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post('/auth/employee-login', { employee_code: code, pin });
      localStorage.setItem('bill4pe_token', data.token);
      localStorage.setItem('bill4pe_user', JSON.stringify(data.user));
      toast.success(`Welcome${data.user?.name ? `, ${data.user.name.split(' ')[0]}` : ''}!`);
      window.location.assign('/app');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Employee login failed');
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-navy text-white grid md:grid-cols-2">
      <div className="hidden md:flex flex-col justify-between p-12">
        <Link to="/" className="self-start bg-white inline-flex items-center p-3 rounded-xl">
          <img src="/logo.png?v=7" alt="BILL4PE" className="h-20 w-auto object-contain" />
        </Link>
        <div>
          <div className="font-display text-5xl font-bold leading-tight">Corporate employee login.</div>
          <p className="text-white/60 mt-4 max-w-sm">Use the memorable six-digit code and PIN issued by your company admin.</p>
        </div>
        <div className="text-xs text-white/40">© 2026 BILL4PE · www.bill4pe.com</div>
      </div>

      <div className="flex items-center justify-center p-6 bg-white text-navy relative">
        <Link to="/login" className="absolute top-4 left-4 inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-semibold text-slate-500 hover:bg-slate-100">
          <ArrowLeft className="w-3.5 h-3.5" /> Back
        </Link>
        <form onSubmit={submit} className="w-full max-w-sm" data-testid="employee-login-form">
          <div className="md:hidden mb-8 bg-white inline-flex items-center p-2 rounded-xl">
            <img src="/logo.png?v=7" alt="BILL4PE" className="h-16 w-auto object-contain" />
          </div>
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.25em] text-brand font-bold"><BadgeCheck className="w-4 h-4" /> Corporate access</div>
          <h1 className="font-display font-bold text-3xl mt-1">Employee sign in</h1>
          <p className="text-sm text-slate-500 mt-1">Both values are exactly six digits.</p>

          <div className="mt-8 space-y-4">
            <div className="relative">
              <Building2 className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                required inputMode="numeric" maxLength={6} placeholder="Employee code"
                value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="pl-10 h-12 rounded-xl border-soft font-mono tracking-[0.25em]"
                data-testid="employee-code-input"
              />
            </div>
            <div className="relative">
              <KeyRound className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                required type="password" inputMode="numeric" maxLength={6} placeholder="6-digit PIN"
                value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="pl-10 h-12 rounded-xl border-soft font-mono tracking-[0.25em]"
                data-testid="employee-pin-input"
              />
            </div>
            <Button type="submit" disabled={loading || code.length !== 6 || pin.length !== 6} className="w-full h-12 bg-brand text-white rounded-full font-semibold">
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null} Sign in
            </Button>
          </div>
          <div className="mt-6 text-center text-sm text-slate-500">Company admin? <Link to="/login" className="text-navy font-semibold underline">Use email login</Link></div>
        </form>
      </div>
    </div>
  );
}
