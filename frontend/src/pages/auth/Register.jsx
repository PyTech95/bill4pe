import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Mail, Lock, User, ArrowLeft, Gift, Building2, UserRound, Check } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth';
import { toast } from 'sonner';
import api from '@/lib/api';

// Mocked corporate subscription plans (Razorpay integration coming later)
const PLAN_OPTIONS = [
  { cycle: 'monthly',   label: 'Monthly',   priceFor: { 50: 1499,  100: 2499  } },
  { cycle: 'quarterly', label: 'Quarterly', priceFor: { 50: 3999,  100: 6499  }, badge: 'Save 10%' },
  { cycle: 'yearly',    label: 'Yearly',    priceFor: { 50: 14999, 100: 23999 }, badge: 'Best value · Save 20%' },
];
const EMPLOYEE_TIERS = [50, 100];

export default function Register() {
  const nav = useNavigate();
  const { register } = useAuth();
  const [searchParams] = useSearchParams();
  const refCode = (searchParams.get('ref') || '').toUpperCase();

  const [userType, setUserType] = useState('individual'); // 'individual' | 'corporate'
  const [form, setForm] = useState({ name: '', email: '', password: '', corporate_name: '' });
  const [cycle, setCycle] = useState('monthly');
  const [employeeTier, setEmployeeTier] = useState(50);
  const [loading, setLoading] = useState(false);
  const [refMeta, setRefMeta] = useState(null);

  useEffect(() => {
    if (!refCode) return;
    api.get(`/referrals/validate/${refCode}`)
      .then(({ data }) => setRefMeta(data))
      .catch(() => setRefMeta(null));
  }, [refCode]);

  const selectedPlan = useMemo(
    () => PLAN_OPTIONS.find((p) => p.cycle === cycle),
    [cycle]
  );
  const planPrice = selectedPlan?.priceFor[employeeTier] || 0;
  const planCode = `${cycle}_${employeeTier}`;

  const submit = async (e) => {
    e.preventDefault();
    if (form.password.length < 6) { toast.error('Password must be 6+ chars'); return; }
    if (userType === 'corporate' && !form.corporate_name.trim()) {
      toast.error('Company name is required for Corporate accounts'); return;
    }
    setLoading(true);
    try {
      const extra = userType === 'corporate'
        ? {
            user_type: 'corporate',
            corporate_name: form.corporate_name.trim(),
            subscription_plan: planCode,
            employee_limit: employeeTier,
          }
        : { user_type: 'individual' };
      const user = await register(
        form.email, form.password, form.name, refMeta ? refCode : null, extra
      );
      const credit = (user?.wallet_balance ?? 50);
      toast.success(
        userType === 'corporate'
          ? `Welcome, ${form.corporate_name}! Free 14-day trial started. ₹${credit.toFixed(0)} added.`
          : `Welcome to BILL4PE! ₹${credit.toFixed(0)} added to your wallet.`
      );
      nav('/app');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Registration failed');
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-navy text-white grid md:grid-cols-2">
      <div className="hidden md:flex flex-col justify-between p-12">
        <Link to="/" className="self-start bg-white inline-flex items-center p-3 rounded-xl">
          <img src="/logo.png" alt="Bill4Pe — The Intelligent Building" className="h-20 w-auto object-contain" />
        </Link>
        <div>
          <div className="font-display text-5xl font-bold leading-tight">Start in 30 seconds.</div>
          <p className="text-white/60 mt-4 max-w-sm">
            Individuals get ₹50 welcome credit. Companies get 14-day trial across 50–100 employees.
          </p>
        </div>
        <div className="text-xs text-white/40">© 2026 BILL4PE · www.bill4pe.com</div>
      </div>

      <div className="flex items-center justify-center p-6 bg-white text-navy relative overflow-y-auto">
        <Link
          to="/"
          data-testid="back-to-landing-btn"
          className="press-down absolute top-4 left-4 inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-semibold text-slate-500 hover:text-navy hover:bg-slate-100"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to home
        </Link>
        <form onSubmit={submit} className="w-full max-w-sm py-12">
          <Link to="/" className="md:hidden mb-8 bg-white inline-flex items-center p-2 rounded-xl">
            <img src="/logo.png" alt="Bill4Pe — The Intelligent Building" className="h-16 w-auto object-contain" />
          </Link>
          <h1 className="font-display font-bold text-3xl">Create account</h1>
          <p className="text-sm text-slate-500 mt-1">Choose how you'll use BILL4PE.</p>

          {/* Individual / Corporate toggle */}
          <div className="mt-5 grid grid-cols-2 gap-2 p-1 bg-slate-100 rounded-xl" data-testid="account-type-toggle">
            <button
              type="button"
              data-testid="account-type-individual"
              onClick={() => setUserType('individual')}
              className={`press-down flex items-center justify-center gap-2 h-11 rounded-lg text-sm font-semibold transition ${
                userType === 'individual' ? 'bg-white text-navy shadow-sm' : 'text-slate-500'
              }`}
            >
              <UserRound className="w-4 h-4" /> Individual
            </button>
            <button
              type="button"
              data-testid="account-type-corporate"
              onClick={() => setUserType('corporate')}
              className={`press-down flex items-center justify-center gap-2 h-11 rounded-lg text-sm font-semibold transition ${
                userType === 'corporate' ? 'bg-white text-navy shadow-sm' : 'text-slate-500'
              }`}
            >
              <Building2 className="w-4 h-4" /> Corporate
            </button>
          </div>

          {refMeta && (
            <div className="mt-4 flex items-start gap-3 rounded-2xl border border-brand/30 bg-brand/5 p-3" data-testid="referral-banner">
              <div className="w-9 h-9 rounded-xl bg-brand text-white grid place-items-center shrink-0">
                <Gift className="w-4 h-4" />
              </div>
              <div className="flex-1">
                <div className="font-semibold text-navy text-sm">{refMeta.referrer_name} invited you</div>
                <div className="text-xs text-slate-500 mt-0.5">
                  You'll both get <span className="font-bold text-brand">₹{refMeta.bonus}</span> wallet credit on signup.
                </div>
              </div>
            </div>
          )}

          <div className="mt-6 space-y-4">
            <div className="relative">
              <User className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                required placeholder={userType === 'corporate' ? 'Your full name (admin)' : 'Full name'}
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="pl-10 h-12 rounded-xl border-soft"
                data-testid="register-name-input"
              />
            </div>

            {userType === 'corporate' && (
              <div className="relative" data-testid="corporate-name-wrap">
                <Building2 className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <Input
                  required placeholder="Company name"
                  value={form.corporate_name}
                  onChange={(e) => setForm({ ...form, corporate_name: e.target.value })}
                  className="pl-10 h-12 rounded-xl border-soft"
                  data-testid="register-corporate-name-input"
                />
              </div>
            )}

            <div className="relative">
              <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                required type="email"
                placeholder={userType === 'corporate' ? 'admin@company.com' : 'you@work.com'}
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

            {userType === 'corporate' && (
              <div className="space-y-3 pt-1" data-testid="corporate-plans-block">
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Choose subscription
                </div>

                {/* Employee tier */}
                <div className="grid grid-cols-2 gap-2">
                  {EMPLOYEE_TIERS.map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setEmployeeTier(n)}
                      data-testid={`plan-employees-${n}`}
                      className={`press-down h-11 rounded-xl text-sm font-semibold border transition ${
                        employeeTier === n
                          ? 'bg-navy text-white border-navy'
                          : 'bg-white text-navy border-slate-200 hover:border-navy/40'
                      }`}
                    >
                      Up to {n} employees
                    </button>
                  ))}
                </div>

                {/* Billing cycle */}
                <div className="space-y-2">
                  {PLAN_OPTIONS.map((p) => {
                    const active = cycle === p.cycle;
                    const price = p.priceFor[employeeTier];
                    return (
                      <button
                        key={p.cycle}
                        type="button"
                        onClick={() => setCycle(p.cycle)}
                        data-testid={`plan-cycle-${p.cycle}`}
                        className={`press-down w-full text-left px-4 py-3 rounded-xl border transition flex items-center justify-between ${
                          active ? 'border-brand bg-brand/5' : 'border-slate-200 hover:border-navy/40'
                        }`}
                      >
                        <div>
                          <div className="font-semibold text-navy text-sm flex items-center gap-2">
                            {p.label}
                            {p.badge && (
                              <span className="text-[10px] uppercase tracking-wider bg-lime/80 text-navy font-bold px-1.5 py-0.5 rounded">
                                {p.badge}
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-slate-500 mt-0.5">
                            ₹{price.toLocaleString('en-IN')} / {p.cycle === 'monthly' ? 'month' : p.cycle === 'quarterly' ? 'quarter' : 'year'}
                          </div>
                        </div>
                        {active && (
                          <div className="w-6 h-6 rounded-full bg-brand text-white grid place-items-center">
                            <Check className="w-3.5 h-3.5" />
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>

                <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 text-xs text-slate-600" data-testid="plan-summary">
                  <div className="font-semibold text-navy">
                    {selectedPlan?.label} · Up to {employeeTier} employees
                  </div>
                  <div className="mt-1">
                    14-day free trial · You won't be charged today. Payments will activate once Razorpay billing is enabled.
                  </div>
                  <div className="mt-1">
                    Plan price: <span className="font-bold text-navy">₹{planPrice.toLocaleString('en-IN')}</span>
                  </div>
                </div>
              </div>
            )}

            <Button
              type="submit" disabled={loading}
              className="press-down w-full h-12 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
              data-testid="register-submit-btn"
            >
              {loading
                ? 'Creating account...'
                : userType === 'corporate'
                  ? 'Start 14-day Corporate trial'
                  : 'Create account & get ₹50'}
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
