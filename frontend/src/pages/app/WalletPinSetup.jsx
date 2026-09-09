import React, { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { LockKeyhole, Loader2, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import api from '@/lib/api';
import { useAuth } from '@/lib/auth';

const digitsOnly = (value) => String(value || '').replace(/\D/g, '').slice(0, 4);

export default function WalletPinSetup() {
  const nav = useNavigate();
  const { user, refreshUser } = useAuth();
  const [pin, setPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [saving, setSaving] = useState(false);

  if (user?.wallet_pin_set) return <Navigate to="/app" replace />;

  const submit = async (e) => {
    e?.preventDefault();
    if (pin.length !== 4 || confirmPin.length !== 4) {
      toast.error('Enter a 4-digit Wallet PIN');
      return;
    }
    if (pin !== confirmPin) {
      toast.error('PINs do not match');
      return;
    }
    setSaving(true);
    try {
      await api.post('/wallet/pin/setup', { pin, confirm_pin: confirmPin });
      await refreshUser();
      toast.success('Wallet PIN set successfully');
      nav('/app', { replace: true });
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not set Wallet PIN');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-white flex items-center justify-center px-5 py-8" data-testid="wallet-pin-setup-page">
      <form onSubmit={submit} className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-navy text-white grid place-items-center mx-auto">
            <LockKeyhole className="w-7 h-7" />
          </div>
          <h1 className="font-display text-2xl font-bold text-navy mt-5">Set Wallet PIN</h1>
          <p className="text-sm text-slate-500 mt-2">
            Create a 4-digit PIN to secure your BILL4PE wallet and billing account.
          </p>
        </div>

        <div className="flat-card p-5 space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-600">4-digit Wallet PIN</label>
            <Input
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              maxLength={4}
              value={pin}
              onChange={(e) => setPin(digitsOnly(e.target.value))}
              placeholder="••••"
              className="mt-1 h-12 text-center text-xl tracking-[0.5em] font-mono"
              data-testid="wallet-pin-input"
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-600">Confirm Wallet PIN</label>
            <Input
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              maxLength={4}
              value={confirmPin}
              onChange={(e) => setConfirmPin(digitsOnly(e.target.value))}
              placeholder="••••"
              className="mt-1 h-12 text-center text-xl tracking-[0.5em] font-mono"
              data-testid="wallet-pin-confirm-input"
            />
          </div>
          <Button className="w-full h-12" type="submit" disabled={saving} data-testid="wallet-pin-submit-btn">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Set Wallet PIN'}
          </Button>
        </div>

        <div className="flex items-start gap-2 text-xs text-slate-400">
          <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5" />
          <span>Your PIN is stored securely and is never displayed in the app.</span>
        </div>
      </form>
    </div>
  );
}
