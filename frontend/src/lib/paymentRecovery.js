// Payment recovery helpers — the frontend never decides payment success on its
// own. It stores only the non-sensitive transaction id locally and always asks
// the backend for the authoritative status (which self-heals a missing bill).
import api from '@/lib/api';

const KEY = 'bill4pe_pending_txn';

export const setPendingTxn = (tid) => { try { localStorage.setItem(KEY, tid); } catch { /* */ } };
export const getPendingTxn = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
export const clearPendingTxn = () => { try { localStorage.removeItem(KEY); } catch { /* */ } };

export const getStatus = async (tid) => {
  const { data } = await api.get(`/payments/${tid}/status`);
  return data;
};

// Poll the authoritative status until the bill is generated (or a terminal
// state is reached). Backoff-friendly; safe to call on app reopen.
export const pollStatus = async (tid, { tries = 10, interval = 1500 } = {}) => {
  let last = null;
  for (let i = 0; i < tries; i++) {
    try {
      last = await getStatus(tid);
      if (last?.bill_status === 'generated' && last?.expense_id) return last;
      if (['failed', 'manual_review', 'refunded'].includes(last?.payment_status)) return last;
    } catch { /* keep trying */ }
    await new Promise((r) => setTimeout(r, interval));
  }
  return last;
};
