import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShieldCheck, Users, Building2, Receipt, TrendingUp, IndianRupee,
  LogOut, Search, RefreshCw, Power, Trash2, Wallet as WalletIcon, ArrowUpRight,
} from 'lucide-react';
import { motion } from 'framer-motion';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth';
import { toast } from 'sonner';
import api from '@/lib/api';

const fmtMoney = (n) => `₹${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const StatCard = ({ icon: Icon, label, value, sub, tone = 'navy', testId }) => (
  <div className="rounded-2xl bg-white border border-slate-200 p-5 shadow-sm" data-testid={testId}>
    <div className="flex items-start justify-between">
      <div className={`w-10 h-10 rounded-xl bg-${tone} text-white grid place-items-center`}>
        <Icon className="w-5 h-5" />
      </div>
      <ArrowUpRight className="w-4 h-4 text-slate-300" />
    </div>
    <div className="mt-4 text-2xl font-display font-bold text-navy">{value}</div>
    <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    {sub && <div className="text-[11px] text-slate-400 mt-2">{sub}</div>}
  </div>
);

const Tab = ({ active, onClick, children, testId }) => (
  <button
    onClick={onClick}
    data-testid={testId}
    className={`press-down px-4 py-2 rounded-full text-sm font-semibold transition ${
      active ? 'bg-navy text-white' : 'bg-white text-slate-500 border border-slate-200 hover:text-navy'
    }`}
  >
    {children}
  </button>
);

export default function SuperAdminDashboard() {
  const nav = useNavigate();
  const { user, logout } = useAuth();
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [tab, setTab] = useState('overview');
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [s, u, c] = await Promise.all([
        api.get('/superadmin/stats'),
        api.get('/superadmin/users', { params: { limit: 200 } }),
        api.get('/superadmin/companies'),
      ]);
      setStats(s.data);
      setUsers(u.data.users || []);
      setCompanies(c.data.companies || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load admin data');
      if (err?.response?.status === 403) nav('/superadmin/login', { replace: true });
    } finally { setLoading(false); }
  };

  useEffect(() => {
    if (!user) { nav('/superadmin/login', { replace: true }); return; }
    if (!user.is_super_admin) {
      toast.error('Super admin access required');
      nav('/', { replace: true });
      return;
    }
    loadAll();
    // eslint-disable-next-line
  }, []);

  const filteredUsers = useMemo(() => {
    if (!q) return users;
    const x = q.toLowerCase();
    return users.filter((u) =>
      (u.email || '').toLowerCase().includes(x) ||
      (u.name || '').toLowerCase().includes(x) ||
      (u.phone || '').toLowerCase().includes(x),
    );
  }, [users, q]);

  const handleToggle = async (u) => {
    try {
      await api.post(`/superadmin/users/${u.id}/toggle-active`, { is_active: !(u.is_active !== false) });
      toast.success('User updated');
      loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed'); }
  };
  const handleDelete = async (u) => {
    if (!window.confirm(`Delete user ${u.email || u.phone}? This cannot be undone.`)) return;
    try {
      await api.delete(`/superadmin/users/${u.id}`);
      toast.success('User deleted');
      loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed'); }
  };
  const handleCreditCompany = async (c) => {
    const raw = window.prompt(`Credit company "${c.name}" wallet by amount (₹):`, '1000');
    if (!raw) return;
    const amount = Number(raw);
    if (!Number.isFinite(amount) || amount <= 0) return toast.error('Invalid amount');
    try {
      const { data } = await api.post(`/superadmin/companies/${c.id}/wallet/credit`, { amount });
      toast.success(`New balance: ${fmtMoney(data.balance)}`);
      loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed'); }
  };
  const handleStatusChange = async (c, status) => {
    try {
      await api.put(`/superadmin/companies/${c.id}`, { subscription_status: status });
      toast.success('Subscription updated');
      loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed'); }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="superadmin-dashboard">
      {/* Top bar */}
      <header className="bg-navy text-white px-5 md:px-10 py-4 sticky top-0 z-30">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/10 grid place-items-center">
              <ShieldCheck className="w-5 h-5 text-lime-300" />
            </div>
            <div>
              <div className="font-display font-bold text-base leading-tight">Bill4Pe · Super Admin</div>
              <div className="text-[11px] text-white/50">Platform control console</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={loadAll}
              disabled={loading}
              className="h-9 px-3 bg-white/10 hover:bg-white/20 text-white rounded-full text-xs"
              data-testid="superadmin-refresh-btn"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
            <Button
              onClick={() => { logout(); nav('/superadmin/login'); }}
              className="h-9 px-3 bg-brand hover:bg-[#1858CC] text-white rounded-full text-xs"
              data-testid="superadmin-logout-btn"
            >
              <LogOut className="w-3.5 h-3.5 mr-1.5" /> Logout
            </Button>
          </div>
        </div>
      </header>

      <div className="px-5 md:px-10 py-6">
        {/* Tabs */}
        <div className="flex flex-wrap gap-2 mb-6">
          <Tab active={tab === 'overview'} onClick={() => setTab('overview')} testId="tab-overview">Overview</Tab>
          <Tab active={tab === 'users'} onClick={() => setTab('users')} testId="tab-users">Users ({users.length})</Tab>
          <Tab active={tab === 'companies'} onClick={() => setTab('companies')} testId="tab-companies">Companies ({companies.length})</Tab>
        </div>

        {tab === 'overview' && stats && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard icon={Users} label="Total users" value={stats.users.total} sub={`+${stats.users.new_last_7d} new in 7 days`} testId="stat-users-total" />
              <StatCard icon={Building2} label="Companies" value={stats.companies.total} sub={`${stats.companies.trial} trial · ${stats.companies.active} active`} testId="stat-companies-total" />
              <StatCard icon={Receipt} label="Expenses logged" value={stats.activity.expenses_total} sub={`${stats.activity.bills_total} bills generated`} testId="stat-expenses-total" />
              <StatCard icon={IndianRupee} label="Platform revenue" value={fmtMoney(stats.revenue.platform_fees_collected)} sub="1% bill fee collected" testId="stat-revenue" />
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div className="rounded-2xl bg-white border border-slate-200 p-6">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400 font-bold">User breakdown</div>
                <div className="mt-4 space-y-3">
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Individual users</span>
                    <span className="font-display font-bold text-navy">{stats.users.individual}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Corporate users</span>
                    <span className="font-display font-bold text-navy">{stats.users.corporate}</span>
                  </div>
                  <div className="flex justify-between border-t border-slate-100 pt-3">
                    <span className="text-sm text-slate-600">New (last 7 days)</span>
                    <span className="font-display font-bold text-emerald-600">+{stats.users.new_last_7d}</span>
                  </div>
                </div>
              </div>
              <div className="rounded-2xl bg-white border border-slate-200 p-6">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400 font-bold">Subscription health</div>
                <div className="mt-4 space-y-3">
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">On trial</span>
                    <span className="font-display font-bold text-amber-600">{stats.companies.trial}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Active (paid)</span>
                    <span className="font-display font-bold text-emerald-600">{stats.companies.active}</span>
                  </div>
                  <div className="flex justify-between border-t border-slate-100 pt-3">
                    <span className="text-sm text-slate-600">Total revenue</span>
                    <span className="font-display font-bold text-navy">{fmtMoney(stats.revenue.platform_fees_collected)}</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {tab === 'users' && (
          <div className="space-y-4">
            <div className="relative max-w-md">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                placeholder="Search by email, name or phone"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="pl-10 h-11 rounded-xl"
                data-testid="superadmin-user-search"
              />
            </div>
            <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
                    <tr>
                      <th className="text-left px-4 py-3">Name</th>
                      <th className="text-left px-4 py-3">Contact</th>
                      <th className="text-left px-4 py-3">Type</th>
                      <th className="text-right px-4 py-3">Wallet</th>
                      <th className="text-center px-4 py-3">Status</th>
                      <th className="text-right px-4 py-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUsers.map((u) => (
                      <tr key={u.id} className="border-t border-slate-100" data-testid={`user-row-${u.id}`}>
                        <td className="px-4 py-3">
                          <div className="font-semibold text-navy">{u.name || '—'}</div>
                          {u.is_super_admin && <div className="text-[10px] text-brand font-bold uppercase">Super admin</div>}
                        </td>
                        <td className="px-4 py-3 text-slate-600">
                          <div>{u.email || '—'}</div>
                          <div className="text-xs text-slate-400">{u.phone || ''}</div>
                        </td>
                        <td className="px-4 py-3 text-slate-600 capitalize">{u.user_type || 'individual'}</td>
                        <td className="px-4 py-3 text-right font-semibold">{fmtMoney(u.wallet_balance)}</td>
                        <td className="px-4 py-3 text-center">
                          <span className={`text-xs font-semibold px-2 py-1 rounded-full ${u.is_active === false ? 'bg-rose-50 text-rose-600' : 'bg-emerald-50 text-emerald-600'}`}>
                            {u.is_active === false ? 'Disabled' : 'Active'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="inline-flex gap-1">
                            <button
                              onClick={() => handleToggle(u)}
                              className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 disabled:opacity-30"
                              disabled={u.is_super_admin}
                              title={u.is_active === false ? 'Enable' : 'Disable'}
                              data-testid={`user-toggle-${u.id}`}
                            >
                              <Power className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDelete(u)}
                              className="p-2 rounded-lg hover:bg-rose-50 text-rose-500 disabled:opacity-30"
                              disabled={u.is_super_admin}
                              title="Delete"
                              data-testid={`user-delete-${u.id}`}
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {filteredUsers.length === 0 && (
                      <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400 text-sm">No users found</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {tab === 'companies' && (
          <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
                  <tr>
                    <th className="text-left px-4 py-3">Company</th>
                    <th className="text-left px-4 py-3">Plan / Status</th>
                    <th className="text-right px-4 py-3">Employees</th>
                    <th className="text-right px-4 py-3">Wallet</th>
                    <th className="text-right px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {companies.map((c) => (
                    <tr key={c.id} className="border-t border-slate-100" data-testid={`company-row-${c.id}`}>
                      <td className="px-4 py-3">
                        <div className="font-semibold text-navy">{c.name}</div>
                        <div className="text-xs text-slate-400">{c.id.slice(0, 8)}</div>
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={c.subscription_status || 'trial'}
                          onChange={(e) => handleStatusChange(c, e.target.value)}
                          className="text-xs border border-slate-200 rounded-lg px-2 py-1 bg-white"
                          data-testid={`company-status-${c.id}`}
                        >
                          <option value="trial">Trial</option>
                          <option value="active">Active</option>
                          <option value="suspended">Suspended</option>
                          <option value="cancelled">Cancelled</option>
                        </select>
                        <div className="text-[10px] text-slate-400 mt-1 capitalize">{c.subscription_plan || 'starter'}</div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="font-semibold">{c.employee_count || 0}</span>
                        <span className="text-slate-400 text-xs"> / {c.employee_limit || 5}</span>
                      </td>
                      <td className="px-4 py-3 text-right font-semibold">{fmtMoney(c.wallet_balance)}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleCreditCompany(c)}
                          className="inline-flex items-center gap-1 text-xs font-semibold px-3 py-1.5 rounded-full bg-navy text-white hover:bg-[#001a44]"
                          data-testid={`company-credit-${c.id}`}
                        >
                          <WalletIcon className="w-3 h-3" /> Credit wallet
                        </button>
                      </td>
                    </tr>
                  ))}
                  {companies.length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400 text-sm">No companies yet</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
