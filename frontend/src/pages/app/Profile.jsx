import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { User, Mail, Phone, Lock, LogOut, Trash2, Loader2, Save, Gift, ChevronRight, Building2, FileBadge } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import api from '@/lib/api';
import { useAuth } from '@/lib/auth';

export default function Profile() {
  const nav = useNavigate();
  const { user, logout, refreshUser } = useAuth();
  const [name, setName] = useState(user?.name || '');
  const [phone, setPhone] = useState(user?.phone?.replace('+91', '') || '');
  const [gstin, setGstin] = useState(user?.gstin || '');
  const [company, setCompany] = useState(user?.company_name || '');
  const [saving, setSaving] = useState(false);
  const [pwd, setPwd] = useState({ current: '', next: '' });
  const [changing, setChanging] = useState(false);

  useEffect(() => {
    if (user) {
      setName(user.name || '');
      setPhone((user.phone || '').replace('+91', ''));
      setGstin(user.gstin || '');
      setCompany(user.company_name || '');
    }
  }, [user]);

  const saveProfile = async () => {
    setSaving(true);
    try {
      await api.put('/auth/me', { name, phone, gstin, company_name: company });
      await refreshUser();
      toast.success('Profile updated');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Update failed');
    } finally { setSaving(false); }
  };

  const changePassword = async () => {
    if (!pwd.current || pwd.next.length < 6) {
      toast.error('Enter current password + new (6+ chars)'); return;
    }
    setChanging(true);
    try {
      await api.post('/auth/change-password', {
        current_password: pwd.current, new_password: pwd.next,
      });
      setPwd({ current: '', next: '' });
      toast.success('Password updated');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Change failed');
    } finally { setChanging(false); }
  };

  const deleteAcct = async () => {
    try {
      await api.delete('/auth/me');
      toast.success('Account deleted');
      logout();
      nav('/');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Delete failed');
    }
  };

  const isPhoneOnly = user?.email?.endsWith('@phone.bill4pe.local');

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Account</div>
        <h1 className="font-display text-2xl font-bold text-navy mt-1">Your profile</h1>
      </div>

      {/* Identity */}
      <div className="flat-card p-5">
        <div className="flex items-center gap-3">
          <div className="w-14 h-14 rounded-2xl bg-navy text-white grid place-items-center font-display font-bold text-xl">
            {(user?.name || 'U')[0].toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="font-display font-bold text-navy text-lg truncate">{user?.name}</div>
            <div className="text-xs text-slate-500 truncate flex items-center gap-1">
              {isPhoneOnly ? <Phone className="w-3 h-3" /> : <Mail className="w-3 h-3" />}
              {isPhoneOnly ? user?.phone : user?.email}
            </div>
          </div>
        </div>
      </div>

      {/* Corporate account badge */}
      {user?.user_type === 'corporate' && (
        <div className="flat-card p-5 border-brand/40 bg-brand/5" data-testid="corporate-badge-card">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-navy text-white grid place-items-center shrink-0">
              <Building2 className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <div className="font-display font-bold text-navy text-base truncate">
                  {user?.corporate_name || 'Corporate account'}
                </div>
                {user?.subscription_status === 'trial' && (
                  <span className="text-[10px] uppercase tracking-wider bg-brand text-white font-bold px-2 py-0.5 rounded">
                    14-day trial
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-600 mt-1">
                {(() => {
                  if (!user?.subscription_plan) return 'No subscription selected';
                  const [cyc] = (user.subscription_plan || '').split('_');
                  const cycLabel = { monthly: 'Monthly', quarterly: 'Quarterly', yearly: 'Yearly' }[cyc] || cyc;
                  return user?.employee_limit
                    ? `${cycLabel} plan · Up to ${user.employee_limit} employees`
                    : `${cycLabel} plan`;
                })()}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">
                Razorpay billing will activate once payments are enabled. You won't be charged today.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit profile */}
      <div className="flat-card p-5 space-y-4">
        <div className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Edit profile</div>
        <div>
          <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Name</label>
          <div className="relative mt-1">
            <User className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input value={name} onChange={(e) => setName(e.target.value)}
                   className="pl-10 h-11 rounded-xl border-soft" data-testid="profile-name-input" />
          </div>
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Phone (optional)</label>
          <div className="relative mt-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 font-mono text-sm text-slate-500">+91</span>
            <Input value={phone} maxLength={10} type="tel"
                   onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(0, 10))}
                   className="pl-12 h-11 rounded-xl border-soft font-mono" data-testid="profile-phone-input" />
          </div>
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Company name (B2B, optional)</label>
          <div className="relative mt-1">
            <Building2 className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input value={company} onChange={(e) => setCompany(e.target.value)}
                   placeholder="e.g. Acme Pvt Ltd"
                   className="pl-10 h-11 rounded-xl border-soft" data-testid="profile-company-input" />
          </div>
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">GSTIN (optional, prints on invoice)</label>
          <div className="relative mt-1">
            <FileBadge className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input value={gstin} maxLength={15}
                   onChange={(e) => setGstin(e.target.value.toUpperCase().slice(0, 15))}
                   placeholder="27ABCDE1234F1Z5"
                   className="pl-10 h-11 rounded-xl border-soft font-mono uppercase" data-testid="profile-gstin-input" />
          </div>
          <div className="text-[10px] text-slate-400 mt-1">15-char GSTIN. Leave blank if not a B2B user.</div>
        </div>
        <Button
          onClick={saveProfile} disabled={saving}
          className="press-down w-full h-11 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
          data-testid="profile-save-btn"
        >
          {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
          Save changes
        </Button>
      </div>

      {/* Change password (email accounts only) */}
      {!isPhoneOnly && (
        <div className="flat-card p-5 space-y-4">
          <div className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Change password</div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Current</label>
            <div className="relative mt-1">
              <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input type="password" value={pwd.current}
                     onChange={(e) => setPwd({ ...pwd, current: e.target.value })}
                     className="pl-10 h-11 rounded-xl border-soft" data-testid="profile-current-pwd" />
            </div>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">New (6+ chars)</label>
            <div className="relative mt-1">
              <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input type="password" value={pwd.next}
                     onChange={(e) => setPwd({ ...pwd, next: e.target.value })}
                     className="pl-10 h-11 rounded-xl border-soft" data-testid="profile-new-pwd" />
            </div>
          </div>
          <Button
            onClick={changePassword} disabled={changing}
            className="press-down w-full h-11 bg-navy text-white hover:bg-[#152042] rounded-full font-semibold"
            data-testid="profile-change-pwd-btn"
          >
            {changing ? 'Updating...' : 'Update password'}
          </Button>
        </div>
      )}

      {/* Refer & earn */}
      <button
        onClick={() => nav('/app/referrals')}
        data-testid="profile-refer-btn"
        className="press-down w-full flat-card p-4 flex items-center gap-3 hover:border-navy"
      >
        <div className="w-10 h-10 rounded-xl bg-brand text-white grid place-items-center">
          <Gift className="w-5 h-5" />
        </div>
        <div className="flex-1 text-left">
          <div className="font-semibold text-navy">Refer & earn ₹50</div>
          <div className="text-xs text-slate-500">Invite a friend, both get wallet credit</div>
        </div>
        <ChevronRight className="w-4 h-4 text-slate-300" />
      </button>

      {/* Sign out */}
      <button
        onClick={() => { logout(); nav('/'); }}
        data-testid="profile-logout-btn"
        className="press-down w-full flat-card p-4 flex items-center gap-3 hover:border-navy"
      >
        <LogOut className="w-5 h-5 text-slate-500" />
        <div className="flex-1 text-left">
          <div className="font-semibold text-navy">Sign out</div>
          <div className="text-xs text-slate-500">You'll be returned to the landing page</div>
        </div>
      </button>

      {/* Danger zone */}
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <button
            data-testid="profile-delete-btn"
            className="press-down w-full flat-card p-4 flex items-center gap-3 border-red-100 hover:border-red-300"
          >
            <Trash2 className="w-5 h-5 text-red-500" />
            <div className="flex-1 text-left">
              <div className="font-semibold text-red-600">Delete account</div>
              <div className="text-xs text-red-400">All expenses, invoices and wallet history will be permanently removed</div>
            </div>
          </button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete your BILL4PE account?</AlertDialogTitle>
            <AlertDialogDescription>
              This cannot be undone. All your expenses, invoices, reports and wallet history
              will be permanently deleted within 30 days.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={deleteAcct}
              className="bg-red-600 hover:bg-red-700"
              data-testid="confirm-delete-account"
            >
              Yes, delete forever
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <div className="text-center text-xs text-slate-400 pb-4">
        BILL4PE · www.bill4pe.com · v1.0
      </div>
    </div>
  );
}
