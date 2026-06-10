import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Building2, Users, ClipboardCheck, Wallet as WalletIcon, Plus, Mail,
  Phone, BadgeCheck, Copy, X, Check, AlertCircle, ChevronRight, Trash2,
  UserPlus, Link as LinkIcon, FileText, ArrowUpRight, Hourglass,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import api from '@/lib/api';
import { useAuth } from '@/lib/auth';

const TABS = [
  { key: 'overview',  label: 'Overview',  icon: Building2 },
  { key: 'employees', label: 'Employees', icon: Users },
  { key: 'approvals', label: 'Approvals', icon: ClipboardCheck },
  { key: 'wallet',    label: 'Wallet',    icon: WalletIcon },
];

const inr = (n) => `₹${Number(n || 0).toLocaleString('en-IN')}`;

export default function CompanyDashboard() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [tab, setTab] = useState('overview');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const isAdmin = user?.role === 'admin' && user?.company_id;

  const refresh = async () => {
    try {
      const { data: d } = await api.get('/company/me');
      setData(d);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Unable to load company');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isAdmin) return;
    refresh();
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <div className="rounded-2xl border border-soft bg-white p-6 text-center">
        <Building2 className="w-10 h-10 text-slate-300 mx-auto" />
        <div className="font-display font-bold text-navy mt-3">Corporate admin only</div>
        <div className="text-sm text-slate-500 mt-1">
          This area is reserved for company administrators.
        </div>
        <Button
          onClick={() => nav('/app')}
          className="mt-4 bg-navy text-white rounded-full px-6"
          data-testid="company-go-home-btn"
        >
          Go to Home
        </Button>
      </div>
    );
  }

  const stats = data?.stats || { employees: 0, pending_approvals: 0, month_spend: 0, wallet_balance: 0 };
  const company = data?.company || {};

  return (
    <div className="space-y-5" data-testid="company-dashboard">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div className="text-[11px] uppercase tracking-[0.3em] text-slate-400 font-bold">
          Company workspace
        </div>
        <h1 className="font-display text-3xl font-bold text-navy mt-1.5 tracking-tight flex items-center gap-2">
          {company.name || 'Your Company'}
        </h1>
        <div className="text-xs text-slate-500 mt-1">
          {(() => {
            const plan = company.subscription_plan || '';
            const m = plan.match(/_(\d+)$/);
            if (plan && m) {
              const seats = m[1];
              const cycle = plan.replace(/_\d+$/, '').replace(/_/g, ' ');
              return `Plan: ${cycle} · ${seats} seats`;
            }
            return plan ? `Plan: ${plan.replace(/_/g, ' ')}` : 'Trial';
          })()}
          {' · '}
          <span className="text-brand font-semibold">{company.subscription_status || 'trial'}</span>
        </div>
      </motion.div>

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3" data-testid="company-kpis">
        <KPI label="Employees" value={stats.employees} icon={Users} testid="kpi-employees" />
        <KPI label="Pending" value={stats.pending_approvals} icon={Hourglass} accent={stats.pending_approvals > 0} testid="kpi-pending" />
        <KPI label="Spend (mo)" value={inr(stats.month_spend)} icon={ArrowUpRight} testid="kpi-spend" />
        <KPI label="Wallet" value={inr(stats.wallet_balance)} icon={WalletIcon} testid="kpi-wallet" />
      </div>

      {/* Tabs */}
      <div className="grid grid-cols-4 gap-1 p-1 bg-slate-100 rounded-2xl" data-testid="company-tabs">
        {TABS.map((t) => {
          const I = t.icon;
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              data-testid={`company-tab-${t.key}`}
              onClick={() => setTab(t.key)}
              className={`press-down flex flex-col items-center gap-1 py-2 rounded-xl text-[11px] font-semibold transition ${
                active ? 'bg-white text-navy shadow-sm' : 'text-slate-500'
              }`}
            >
              <I className="w-4 h-4" />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      {loading ? (
        <div className="text-center text-sm text-slate-400 py-8">Loading...</div>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}
          >
            {tab === 'overview'  && <Overview stats={stats} setTab={setTab} />}
            {tab === 'employees' && <Employees onChange={refresh} limit={company.employee_limit} count={stats.employees} />}
            {tab === 'approvals' && <Approvals onChange={refresh} />}
            {tab === 'wallet'    && <CompanyWallet balance={stats.wallet_balance} onChange={refresh} />}
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}

/* --------- KPI Card --------- */
const KPI = ({ label, value, icon: Icon, accent, testid }) => (
  <div
    className={`rounded-2xl border p-3 ${
      accent ? 'border-brand bg-brand/5' : 'border-soft bg-white'
    }`}
    data-testid={testid}
  >
    <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
      <Icon className="w-3.5 h-3.5" />
      {label}
    </div>
    <div className="font-mono font-bold text-navy text-xl mt-1">{value}</div>
  </div>
);

/* --------- Overview --------- */
const Overview = ({ stats, setTab }) => (
  <div className="space-y-3">
    <Action
      label="Review pending bills"
      desc={stats.pending_approvals > 0
        ? `${stats.pending_approvals} employee bill${stats.pending_approvals === 1 ? '' : 's'} need your decision.`
        : 'You are all caught up.'}
      onClick={() => setTab('approvals')}
      icon={ClipboardCheck}
      accent={stats.pending_approvals > 0}
      testid="overview-approvals-cta"
    />
    <Action
      label="Manage employees"
      desc="Add, invite or update your team."
      onClick={() => setTab('employees')}
      icon={Users}
      testid="overview-employees-cta"
    />
    <Action
      label="Recharge company wallet"
      desc="Used to pay ₹5 / bill across all employees."
      onClick={() => setTab('wallet')}
      icon={WalletIcon}
      testid="overview-wallet-cta"
    />
  </div>
);

const Action = ({ label, desc, onClick, icon: Icon, accent, testid }) => (
  <button
    onClick={onClick}
    data-testid={testid}
    className={`press-down w-full text-left rounded-2xl border p-4 flex items-center gap-3 hover:border-navy transition ${
      accent ? 'border-brand bg-brand/5' : 'border-soft bg-white'
    }`}
  >
    <div className={`w-10 h-10 rounded-xl grid place-items-center shrink-0 ${
      accent ? 'bg-brand text-white' : 'bg-slate-100 text-navy'
    }`}>
      <Icon className="w-5 h-5" />
    </div>
    <div className="flex-1 min-w-0">
      <div className="font-display font-bold text-navy text-sm">{label}</div>
      <div className="text-xs text-slate-500 mt-0.5">{desc}</div>
    </div>
    <ChevronRight className="w-4 h-4 text-slate-300" />
  </button>
);

/* --------- Employees --------- */
const Employees = ({ onChange, limit, count }) => {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null); // null | 'create' | 'invite'
  const [credModal, setCredModal] = useState(null); // {email, password}
  const [inviteModal, setInviteModal] = useState(null); // {link}

  const load = async () => {
    try {
      const { data } = await api.get('/company/employees');
      setEmployees(data.employees || []);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const remove = async (id) => {
    if (!window.confirm('Remove this employee? Their bills will remain in records.')) return;
    try {
      await api.delete(`/company/employees/${id}`);
      toast.success('Employee removed');
      load(); onChange?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to remove');
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-slate-500">
          {count} / {limit || '∞'} seats used
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => setModal('invite')}
            data-testid="emp-invite-btn"
            className="press-down h-9 px-3 text-xs bg-white text-navy border border-soft hover:border-navy rounded-full"
          >
            <LinkIcon className="w-3.5 h-3.5 mr-1" /> Invite link
          </Button>
          <Button
            onClick={() => setModal('create')}
            data-testid="emp-add-btn"
            className="press-down h-9 px-3 text-xs bg-navy text-white hover:bg-[#0F1631] rounded-full"
          >
            <UserPlus className="w-3.5 h-3.5 mr-1" /> Add
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="text-sm text-slate-400 text-center py-6">Loading employees...</div>
      ) : employees.length === 0 ? (
        <div className="rounded-2xl border border-soft bg-white p-6 text-center" data-testid="emp-empty">
          <Users className="w-10 h-10 text-slate-300 mx-auto" />
          <div className="font-display font-bold text-navy mt-3">No employees yet</div>
          <div className="text-sm text-slate-500 mt-1">
            Add your first team member to enable bill submission.
          </div>
        </div>
      ) : (
        <div className="space-y-2" data-testid="emp-list">
          {employees.map((e) => (
            <div
              key={e.id}
              data-testid={`emp-row-${e.id}`}
              className="rounded-2xl border border-soft bg-white p-3 flex items-center gap-3"
            >
              <div className="w-10 h-10 rounded-full bg-navy text-brand grid place-items-center font-display font-bold shrink-0">
                {(e.name || '?').slice(0, 1).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <div className="font-display font-bold text-navy text-sm truncate">{e.name}</div>
                  {e.status === 'pending_invite' && (
                    <span className="text-[9px] font-bold uppercase tracking-wider bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded">
                      Invited
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-500 truncate">
                  {e.email}
                  {e.department ? ` · ${e.department}` : ''}
                  {e.designation ? ` · ${e.designation}` : ''}
                </div>
              </div>
              <button
                onClick={() => remove(e.id)}
                data-testid={`emp-remove-${e.id}`}
                className="press-down w-8 h-8 rounded-full grid place-items-center text-slate-400 hover:bg-red-50 hover:text-red-600 transition"
                title="Remove employee"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {modal && (
        <EmployeeModal
          mode={modal}
          onClose={() => setModal(null)}
          onCreated={(payload) => {
            setModal(null); load(); onChange?.();
            if (payload?.credentials) setCredModal(payload.credentials);
            if (payload?.invite) {
              const url = `${window.location.origin}/accept-invite?token=${payload.invite.token}`;
              setInviteModal({ link: url, name: payload.employee?.name });
            }
          }}
        />
      )}
      {credModal && <CredsModal info={credModal} onClose={() => setCredModal(null)} />}
      {inviteModal && <InviteModal info={inviteModal} onClose={() => setInviteModal(null)} />}
    </div>
  );
};

const EmployeeModal = ({ mode, onClose, onCreated }) => {
  const isInvite = mode === 'invite';
  const [form, setForm] = useState({
    name: '', email: '', phone: '', department: '', designation: '',
    employee_id: '', monthly_cap: '',
  });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = {
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || null,
        department: form.department.trim() || null,
        designation: form.designation.trim() || null,
        employee_id: form.employee_id.trim() || null,
        monthly_cap: form.monthly_cap ? Number(form.monthly_cap) : null,
      };
      const { data } = await api.post(
        isInvite ? '/company/employees/invite' : '/company/employees',
        payload,
      );
      toast.success(isInvite ? 'Invite created' : 'Employee added');
      onCreated(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed');
    } finally { setBusy(false); }
  };

  return (
    <ModalShell onClose={onClose} title={isInvite ? 'Invite employee' : 'Add employee'} testid="emp-modal">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Full name *">
          <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            data-testid="emp-form-name" className="h-11 rounded-xl border-soft" />
        </Field>
        <Field label="Email *">
          <Input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
            data-testid="emp-form-email" className="h-11 rounded-xl border-soft" />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Phone">
            <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })}
              data-testid="emp-form-phone" className="h-11 rounded-xl border-soft" placeholder="10 digits" />
          </Field>
          <Field label="Employee ID">
            <Input value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
              data-testid="emp-form-empid" className="h-11 rounded-xl border-soft" placeholder="E.g. EMP-101" />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Department">
            <Input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })}
              data-testid="emp-form-dept" className="h-11 rounded-xl border-soft" placeholder="Sales" />
          </Field>
          <Field label="Designation">
            <Input value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })}
              data-testid="emp-form-desig" className="h-11 rounded-xl border-soft" placeholder="Manager" />
          </Field>
        </div>
        <Field label="Monthly spend cap (₹)">
          <Input type="number" min="0" value={form.monthly_cap}
            onChange={(e) => setForm({ ...form, monthly_cap: e.target.value })}
            data-testid="emp-form-cap" className="h-11 rounded-xl border-soft" placeholder="Leave blank for unlimited" />
        </Field>

        <Button
          type="submit" disabled={busy}
          data-testid="emp-form-submit"
          className="press-down w-full h-11 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
        >
          {busy ? 'Saving...' : isInvite ? 'Generate invite link' : 'Create with temp password'}
        </Button>
      </form>
    </ModalShell>
  );
};

const CredsModal = ({ info, onClose }) => (
  <ModalShell onClose={onClose} title="Employee credentials" testid="creds-modal">
    <div className="rounded-xl bg-lime/30 border border-lime p-3 text-xs text-navy">
      <div className="flex items-start gap-2">
        <BadgeCheck className="w-4 h-4 mt-0.5 shrink-0" />
        <div>Share these securely. The employee can change the password after first login.</div>
      </div>
    </div>
    <div className="mt-3 space-y-2">
      <CopyRow label="Email" value={info.email} testid="creds-email" />
      <CopyRow label="Temporary password" value={info.temp_password} testid="creds-password" mono />
    </div>
    <Button
      onClick={onClose}
      data-testid="creds-modal-close"
      className="mt-4 w-full h-11 bg-navy text-white rounded-full"
    >
      Done
    </Button>
  </ModalShell>
);

const InviteModal = ({ info, onClose }) => (
  <ModalShell onClose={onClose} title="Invite link generated" testid="invite-modal">
    <div className="text-xs text-slate-500 mb-2">
      Send this link to <b className="text-navy">{info.name}</b>. It expires in 14 days.
    </div>
    <CopyRow label="Invite link" value={info.link} testid="invite-link" wrap />
    <Button
      onClick={onClose}
      data-testid="invite-modal-close"
      className="mt-4 w-full h-11 bg-navy text-white rounded-full"
    >
      Done
    </Button>
  </ModalShell>
);

const CopyRow = ({ label, value, testid, mono, wrap }) => {
  const copy = () => {
    navigator.clipboard?.writeText(value);
    toast.success('Copied');
  };
  return (
    <div className="rounded-xl border border-soft p-3" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">{label}</div>
      <div className="flex items-center gap-2 mt-1">
        <div className={`flex-1 ${mono ? 'font-mono' : ''} text-sm text-navy ${wrap ? 'break-all' : 'truncate'}`}>
          {value}
        </div>
        <button onClick={copy} className="press-down p-2 rounded-lg hover:bg-slate-100"
          data-testid={`${testid}-copy`}>
          <Copy className="w-4 h-4 text-slate-500" />
        </button>
      </div>
    </div>
  );
};

const Field = ({ label, children }) => (
  <label className="block">
    <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-1">{label}</div>
    {children}
  </label>
);

const ModalShell = ({ onClose, title, children, testid }) => (
  <motion.div
    initial={{ opacity: 0 }} animate={{ opacity: 1 }}
    className="fixed inset-0 z-50 grid place-items-end sm:place-items-center bg-black/50 backdrop-blur-sm"
    onClick={onClose}
    data-testid={testid}
  >
    <motion.div
      initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
      onClick={(e) => e.stopPropagation()}
      className="w-full sm:max-w-md bg-white rounded-t-3xl sm:rounded-3xl p-5 sm:m-4 max-h-[92vh] overflow-y-auto"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="font-display font-bold text-navy">{title}</div>
        <button onClick={onClose} className="press-down p-1.5 rounded-full hover:bg-slate-100"
          data-testid={`${testid}-close`}>
          <X className="w-4 h-4 text-slate-500" />
        </button>
      </div>
      {children}
    </motion.div>
  </motion.div>
);

/* --------- Approvals --------- */
const Approvals = ({ onChange }) => {
  const [tab, setTab] = useState('pending');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [rejecting, setRejecting] = useState(null); // expense id
  const [reason, setReason] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/company/approvals?status=${tab}`);
      setItems(data.approvals || []);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [tab]);

  const approve = async (id) => {
    try {
      await api.post(`/company/approvals/${id}/approve`, {});
      toast.success('Approved');
      load(); onChange?.();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed'); }
  };
  const reject = async (id) => {
    if (!reason.trim()) { toast.error('Please enter a reason'); return; }
    try {
      await api.post(`/company/approvals/${id}/reject`, { reason });
      toast.success('Rejected');
      setRejecting(null); setReason('');
      load(); onChange?.();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed'); }
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-1 p-1 bg-slate-100 rounded-xl">
        {['pending', 'approved', 'rejected'].map((s) => (
          <button
            key={s}
            data-testid={`approvals-tab-${s}`}
            onClick={() => setTab(s)}
            className={`press-down h-9 rounded-lg text-xs font-semibold transition capitalize ${
              tab === s ? 'bg-white text-navy shadow-sm' : 'text-slate-500'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-sm text-slate-400 text-center py-6">Loading...</div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-soft bg-white p-6 text-center" data-testid="approvals-empty">
          <ClipboardCheck className="w-10 h-10 text-slate-300 mx-auto" />
          <div className="font-display font-bold text-navy mt-3">
            No {tab} bills
          </div>
        </div>
      ) : (
        <div className="space-y-2" data-testid="approvals-list">
          {items.map((e) => (
            <div key={e.id} data-testid={`approval-row-${e.id}`}
              className="rounded-2xl border border-soft bg-white p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <div className="font-display font-bold text-navy text-sm truncate">
                      {e.submitter?.name || 'Employee'}
                    </div>
                    <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
                      {e.category}{e.sub_category ? ` · ${e.sub_category}` : ''}
                    </span>
                  </div>
                  <div className="text-xs text-slate-500 truncate">
                    {e.submitter?.department || '—'} · {(e.created_at || '').slice(0, 10)}
                  </div>
                  <div className="font-mono font-bold text-navy mt-1">{inr(e.total)}</div>
                </div>
                {tab === 'pending' && (
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      onClick={() => approve(e.id)}
                      data-testid={`approve-btn-${e.id}`}
                      className="press-down w-9 h-9 rounded-full bg-lime text-navy grid place-items-center"
                      title="Approve"
                    >
                      <Check className="w-4 h-4" strokeWidth={2.5} />
                    </button>
                    <button
                      onClick={() => { setRejecting(e.id); setReason(''); }}
                      data-testid={`reject-btn-${e.id}`}
                      className="press-down w-9 h-9 rounded-full bg-red-50 text-red-600 grid place-items-center"
                      title="Reject"
                    >
                      <X className="w-4 h-4" strokeWidth={2.5} />
                    </button>
                  </div>
                )}
                {tab === 'rejected' && e.approval_note && (
                  <div className="text-[11px] text-red-600 max-w-[40%] text-right">
                    {e.approval_note}
                  </div>
                )}
              </div>

              {rejecting === e.id && (
                <div className="mt-3 pt-3 border-t border-soft" data-testid={`reject-form-${e.id}`}>
                  <Input
                    placeholder="Reason for rejection (required)"
                    value={reason}
                    onChange={(ev) => setReason(ev.target.value)}
                    data-testid={`reject-reason-${e.id}`}
                    className="h-10 rounded-xl border-soft"
                  />
                  <div className="flex gap-2 mt-2">
                    <Button
                      onClick={() => reject(e.id)}
                      data-testid={`reject-confirm-${e.id}`}
                      className="flex-1 h-9 bg-red-600 text-white hover:bg-red-700 rounded-full text-xs"
                    >
                      Confirm reject
                    </Button>
                    <Button
                      onClick={() => { setRejecting(null); setReason(''); }}
                      data-testid={`reject-cancel-${e.id}`}
                      className="flex-1 h-9 bg-white text-navy border border-soft rounded-full text-xs"
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

/* --------- Wallet --------- */
const CompanyWallet = ({ balance, onChange }) => {
  const [amount, setAmount] = useState('500');
  const [busy, setBusy] = useState(false);
  const [txns, setTxns] = useState([]);

  const load = async () => {
    try {
      const { data } = await api.get('/company/wallet');
      setTxns(data.transactions || []);
    } catch { /* ignore */ }
  };
  useEffect(() => { load(); }, []);

  const recharge = async () => {
    const v = Number(amount);
    if (!v || v <= 0) { toast.error('Enter a positive amount'); return; }
    setBusy(true);
    try {
      await api.post('/company/wallet/recharge', { amount: v });
      toast.success(`₹${v} added to company wallet (mock)`);
      load(); onChange?.();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-3">
      <div className="rounded-2xl bg-navy text-white p-4">
        <div className="text-[10px] uppercase tracking-[0.25em] text-brand/80 font-bold">
          Company wallet
        </div>
        <div className="font-mono font-bold text-3xl mt-1" data-testid="cw-balance">
          {inr(balance)}
        </div>
        <div className="text-[11px] text-white/60 mt-1">
          Pays ₹5 per generated bill across all employees.
        </div>
      </div>

      <div className="rounded-2xl border border-soft bg-white p-4">
        <div className="text-xs font-semibold text-navy">Recharge (mock)</div>
        <div className="flex gap-2 mt-2">
          {[500, 1000, 5000].map((v) => (
            <button
              key={v}
              onClick={() => setAmount(String(v))}
              data-testid={`cw-quick-${v}`}
              className={`press-down flex-1 h-9 rounded-full border text-xs font-semibold transition ${
                Number(amount) === v ? 'bg-navy text-white border-navy' : 'bg-white text-navy border-soft'
              }`}
            >
              ₹{v.toLocaleString('en-IN')}
            </button>
          ))}
        </div>
        <div className="flex gap-2 mt-2">
          <Input
            type="number" min="0" value={amount}
            onChange={(e) => setAmount(e.target.value)}
            data-testid="cw-amount-input"
            className="flex-1 h-11 rounded-xl border-soft"
          />
          <Button
            onClick={recharge} disabled={busy}
            data-testid="cw-recharge-btn"
            className="press-down h-11 px-5 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
          >
            {busy ? '...' : 'Add'}
          </Button>
        </div>
        <div className="text-[11px] text-slate-400 mt-2 flex items-start gap-1.5">
          <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
          Razorpay billing will activate this flow with real money soon.
        </div>
      </div>

      {txns.length > 0 && (
        <div className="rounded-2xl border border-soft bg-white p-4">
          <div className="text-xs font-semibold text-navy mb-2">Recent transactions</div>
          <div className="space-y-2" data-testid="cw-txns">
            {txns.slice(0, 8).map((t) => (
              <div key={t.id} className="flex items-center justify-between text-sm">
                <div className="min-w-0 flex-1">
                  <div className="text-navy text-xs truncate">{t.reason}</div>
                  <div className="text-[10px] text-slate-400">{(t.created_at || '').slice(0, 10)}</div>
                </div>
                <div className={`font-mono font-bold ${t.type === 'credit' ? 'text-emerald-600' : 'text-red-500'}`}>
                  {t.type === 'credit' ? '+' : '−'}₹{Number(t.amount).toFixed(0)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
