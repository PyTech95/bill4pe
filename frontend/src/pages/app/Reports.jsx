import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  FileBarChart, Download, Plus, ChevronRight, Loader2, Check, Trash2, Calendar, Building2,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger, SheetDescription,
} from '@/components/ui/sheet';
import { toast } from 'sonner';
import api, { API } from '@/lib/api';
import { catByKey } from '@/lib/categories';

const monthLabel = () => {
  const d = new Date();
  return d.toLocaleString('en-IN', { month: 'long', year: 'numeric' }) + ' expenses';
};

export default function Reports() {
  const nav = useNavigate();
  const [reports, setReports] = useState([]);
  const [expenses, setExpenses] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [title, setTitle] = useState(monthLabel());
  const [notes, setNotes] = useState('');
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState(false);

  const load = async () => {
    const [r, e] = await Promise.all([
      api.get('/reports'),
      api.get('/expenses'),
    ]);
    setReports(r.data?.reports || []);
    setExpenses(e.data?.expenses || []);
  };
  useEffect(() => { load(); }, []);

  const total = useMemo(
    () => expenses.filter((e) => selected.has(e.id)).reduce((s, e) => s + Number(e.total || 0), 0),
    [selected, expenses]
  );

  const toggle = (id) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  const selectAll = () => {
    if (selected.size === expenses.length) setSelected(new Set());
    else setSelected(new Set(expenses.map((e) => e.id)));
  };

  const create = async () => {
    if (selected.size === 0) { toast.error('Select at least one expense'); return; }
    setCreating(true);
    try {
      const { data } = await api.post('/reports', {
        title: title.trim() || 'Expense Report',
        expense_ids: [...selected],
        notes: notes.trim() || null,
      });
      toast.success(`Report created (${data.expense_count} bills, ₹${data.total.toFixed(2)})`);
      setSelected(new Set());
      setNotes('');
      setOpen(false);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not create report');
    } finally { setCreating(false); }
  };

  const removeReport = async (id) => {
    if (!window.confirm('Delete this report?')) return;
    try {
      await api.delete(`/reports/${id}`);
      await load();
      toast.success('Report deleted');
    } catch { toast.error('Could not delete'); }
  };

  const pdfUrl = (id) => {
    const token = localStorage.getItem('bill4pe_token');
    return `${API}/reports/${id}/pdf?token=${encodeURIComponent(token || '')}`;
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Reimbursement</div>
        <div className="flex items-start justify-between gap-3">
          <h1 className="font-display text-2xl font-bold text-navy mt-1">Expense reports</h1>
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <button
                data-testid="reports-create-btn"
                className="press-down inline-flex items-center gap-1.5 h-9 px-3 rounded-full bg-brand text-white text-xs font-semibold hover:bg-[#1858CC]"
              >
                <Plus className="w-3.5 h-3.5" /> New report
              </button>
            </SheetTrigger>
            <SheetContent side="bottom" className="rounded-t-3xl border-0 px-5 pb-8 pt-7 max-h-[90vh] overflow-y-auto">
              <SheetHeader className="text-left">
                <SheetTitle className="font-display text-2xl text-navy">Bundle expenses into a report</SheetTitle>
                <SheetDescription className="text-slate-500">
                  Select bills to consolidate into a single PDF for monthly reimbursement.
                </SheetDescription>
              </SheetHeader>

              <div className="mt-5 space-y-4">
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Report title</label>
                  <Input value={title} onChange={(e) => setTitle(e.target.value)}
                         className="mt-1 h-11 rounded-xl border-soft"
                         data-testid="report-title-input" />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Notes (optional)</label>
                  <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
                            className="mt-1 rounded-xl border-soft text-sm"
                            data-testid="report-notes-input" />
                </div>

                <div className="flex items-center justify-between pt-2">
                  <button onClick={selectAll} className="text-xs text-navy font-semibold underline"
                          data-testid="report-select-all">
                    {selected.size === expenses.length ? 'Clear all' : 'Select all'}
                  </button>
                  <div className="text-xs">
                    <span className="text-slate-400">Selected: </span>
                    <span className="font-mono font-bold text-navy">{selected.size}</span>
                    <span className="text-slate-400 mx-1">·</span>
                    <span className="font-mono font-bold text-brand">₹{total.toFixed(2)}</span>
                  </div>
                </div>

                <div className="max-h-[40vh] overflow-y-auto space-y-2 border-t border-soft pt-3">
                  {expenses.length === 0 && (
                    <div className="text-center py-8 text-sm text-slate-400">
                      No expenses to bundle yet.
                    </div>
                  )}
                  {expenses.map((e) => {
                    const c = catByKey(e.category);
                    const Icon = c?.icon || Building2;
                    const isOn = selected.has(e.id);
                    return (
                      <label
                        key={e.id}
                        data-testid={`report-pick-${e.id}`}
                        className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition ${isOn ? 'border-brand bg-brand/5' : 'border-soft hover:border-navy'}`}
                      >
                        <Checkbox checked={isOn} onCheckedChange={() => toggle(e.id)} />
                        <div className="w-9 h-9 rounded-lg bg-navy text-white grid place-items-center shrink-0">
                          <Icon className="w-4 h-4" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-semibold text-navy truncate">
                            {e.payment?.merchant_name || (c?.label + ' expense')}
                          </div>
                          <div className="text-[10px] text-slate-400 font-mono">
                            {(e.created_at || '').slice(0, 16).replace('T', ' ')} · {c?.label}
                          </div>
                        </div>
                        <div className="font-mono text-sm font-bold text-navy">₹ {Number(e.total).toFixed(0)}</div>
                      </label>
                    );
                  })}
                </div>

                <Button
                  onClick={create} disabled={creating || selected.size === 0}
                  className="press-down w-full h-12 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
                  data-testid="report-create-confirm-btn"
                >
                  {creating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <FileBarChart className="w-4 h-4 mr-2" />}
                  Generate report ({selected.size} bills · ₹{total.toFixed(2)})
                </Button>
              </div>
            </SheetContent>
          </Sheet>
        </div>
        <p className="text-sm text-slate-500 mt-1">Consolidate multiple bills into one corporate-ready PDF.</p>
      </div>

      {/* Reports list */}
      {reports.length === 0 ? (
        <div className="flat-card p-10 text-center">
          <FileBarChart className="w-10 h-10 text-slate-300 mx-auto" strokeWidth={1.4} />
          <h3 className="font-display font-bold text-navy mt-3">No reports yet</h3>
          <p className="text-sm text-slate-500 mt-1">Bundle multiple bills into one PDF for easier reimbursement filing.</p>
          <button
            onClick={() => setOpen(true)}
            className="press-down mt-5 inline-flex items-center gap-1.5 bg-brand text-white px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-[#1858CC]"
            data-testid="reports-empty-cta"
          >
            <Plus className="w-4 h-4" /> Create your first report
          </button>
        </div>
      ) : (
        <motion.div
          initial="hidden" animate="show"
          variants={{ show: { transition: { staggerChildren: 0.04 } } }}
          className="space-y-2"
        >
          {reports.map((r) => (
            <motion.div
              key={r.id}
              variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}
              className="flat-card p-4"
              data-testid={`report-${r.id}`}
            >
              <div className="flex items-start gap-3">
                <div className="w-11 h-11 rounded-xl bg-brand text-white grid place-items-center shrink-0">
                  <FileBarChart className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-display font-bold text-navy truncate">{r.title}</div>
                  <div className="text-[10px] text-slate-400 font-mono mt-0.5 flex items-center gap-1">
                    <Calendar className="w-3 h-3" /> {(r.created_at || '').slice(0, 16).replace('T', ' ')} · {r.expense_count} bills
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-mono font-bold text-navy">₹ {r.total.toFixed(2)}</div>
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-soft flex items-center gap-2">
                <a
                  href={pdfUrl(r.id)} target="_blank" rel="noopener noreferrer"
                  className="press-down flex-1 inline-flex items-center justify-center gap-1.5 h-9 rounded-full bg-navy text-white text-xs font-semibold hover:bg-[#152042]"
                  data-testid={`report-download-${r.id}`}
                >
                  <Download className="w-3.5 h-3.5" /> Download PDF
                </a>
                <button
                  onClick={() => removeReport(r.id)}
                  className="press-down h-9 w-9 rounded-full border border-soft grid place-items-center hover:border-red-300 hover:text-red-600"
                  data-testid={`report-delete-${r.id}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
