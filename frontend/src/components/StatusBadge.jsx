const STYLES = {
  paid: "bg-emerald-50 text-emerald-700 border-emerald-200",
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  overdue: "bg-rose-50 text-rose-700 border-rose-200",
  draft: "bg-slate-100 text-slate-600 border-slate-200",
};

export function StatusBadge({ status, testid }) {
  return (
    <span
      data-testid={testid || `status-badge-${status}`}
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full border text-xs font-semibold capitalize ${STYLES[status] || STYLES.draft}`}
    >
      {status}
    </span>
  );
}
