import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Phone, Smartphone, Loader2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp';
import { toast } from 'sonner';
import api from '@/lib/api';
import Logo from '@/components/Logo';

export default function PhoneLogin() {
  const nav = useNavigate();
  const [step, setStep] = useState('phone'); // phone | otp
  const [phone, setPhone] = useState('');
  const [name, setName] = useState('');
  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);
  const [resendIn, setResendIn] = useState(0);

  useEffect(() => {
    if (resendIn <= 0) return;
    const id = setInterval(() => setResendIn((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, [resendIn]);

  const requestOtp = async () => {
    const digits = phone.replace(/\D/g, '').slice(-10);
    if (digits.length !== 10) { toast.error('Enter a valid 10-digit number'); return; }
    setLoading(true);
    try {
      await api.post('/auth/otp/request', { phone: digits, name });
      toast.success('Demo OTP is 123456');
      setStep('otp');
      setResendIn(30);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not send OTP');
    } finally { setLoading(false); }
  };

  const verifyOtp = async () => {
    if (otp.length !== 6) { toast.error('Enter the 6-digit OTP'); return; }
    setLoading(true);
    try {
      const digits = phone.replace(/\D/g, '').slice(-10);
      const { data } = await api.post('/auth/otp/verify', { phone: digits, otp, name });
      localStorage.setItem('bill4pe_token', data.token);
      localStorage.setItem('bill4pe_user', JSON.stringify(data.user));
      toast.success(`Welcome${data.user?.name ? ', ' + data.user.name.split(' ')[0] : ''}!`);
      // Hard reload so AuthProvider picks up the new user
      window.location.assign('/app');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Invalid OTP');
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-navy text-white grid md:grid-cols-2">
      <div className="hidden md:flex flex-col justify-between p-12">
        <Link to="/" className="self-start">
          <img src="/logo.png" alt="Bill4Pe" className="h-12 w-auto rounded-lg" />
        </Link>
        <div>
          <div className="font-display text-5xl font-bold leading-tight">Sign in with your phone.</div>
          <p className="text-white/60 mt-4 max-w-sm">Fastest way in. Demo OTP is <span className="text-lime font-mono">123456</span>.</p>
        </div>
        <div className="text-xs text-white/40">© 2026 BILL4PE · billforpay.com</div>
      </div>

      <div className="flex items-center justify-center p-6 bg-white text-navy">
        <div className="w-full max-w-sm">
          <Link to="/" className="md:hidden block mb-8">
            <img src="/logo.png" alt="Bill4Pe" className="h-12 w-auto rounded-lg" />
          </Link>

          {step === 'phone' && (
            <>
              <h1 className="font-display font-bold text-3xl">Phone login</h1>
              <p className="text-sm text-slate-500 mt-1">We'll send a 6-digit OTP to verify.</p>
              <div className="mt-8 space-y-5">
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Name (optional)</label>
                  <Input
                    placeholder="Your full name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="mt-1 h-12 rounded-xl border-soft"
                    data-testid="otp-name-input"
                  />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Mobile number</label>
                  <div className="relative mt-1">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 font-mono text-sm text-slate-500">+91</span>
                    <Input
                      type="tel" maxLength={10}
                      placeholder="98765 43210"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(0, 10))}
                      className="pl-12 h-12 rounded-xl border-soft font-mono tracking-widest"
                      data-testid="otp-phone-input"
                    />
                  </div>
                </div>
                <Button
                  onClick={requestOtp} disabled={loading}
                  className="press-down w-full h-12 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
                  data-testid="otp-request-btn"
                >
                  {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Phone className="w-4 h-4 mr-2" />}
                  Send OTP
                </Button>
              </div>
              <div className="mt-6 text-sm text-slate-500 text-center">
                Prefer email?{' '}
                <Link to="/login" className="text-navy font-semibold underline" data-testid="link-email-login">
                  Sign in with email
                </Link>
              </div>
            </>
          )}

          {step === 'otp' && (
            <>
              <h1 className="font-display font-bold text-3xl">Enter OTP</h1>
              <p className="text-sm text-slate-500 mt-1">
                Sent to <span className="font-mono text-navy font-semibold">+91 {phone}</span>
              </p>
              <div className="mt-2 inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider bg-lime/30 text-navy px-2 py-1 rounded-full font-bold">
                <Smartphone className="w-3 h-3" /> Demo mode · OTP is 123456
              </div>

              <div className="mt-8 flex justify-center">
                <InputOTP maxLength={6} value={otp} onChange={setOtp} data-testid="otp-input">
                  <InputOTPGroup>
                    {[0, 1, 2, 3, 4, 5].map((i) => (
                      <InputOTPSlot key={i} index={i} className="h-12 w-12 text-lg font-mono" />
                    ))}
                  </InputOTPGroup>
                </InputOTP>
              </div>

              <Button
                onClick={verifyOtp} disabled={loading || otp.length !== 6}
                className="press-down w-full h-12 mt-7 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
                data-testid="otp-verify-btn"
              >
                {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                Verify & continue
              </Button>

              <div className="mt-5 flex items-center justify-between text-sm">
                <button
                  className="text-slate-500 underline"
                  onClick={() => { setStep('phone'); setOtp(''); }}
                  data-testid="otp-change-number"
                >Change number</button>
                <button
                  className="text-navy font-semibold disabled:text-slate-400 disabled:no-underline underline"
                  disabled={resendIn > 0 || loading}
                  onClick={requestOtp}
                  data-testid="otp-resend"
                >
                  {resendIn > 0 ? `Resend in ${resendIn}s` : 'Resend OTP'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
