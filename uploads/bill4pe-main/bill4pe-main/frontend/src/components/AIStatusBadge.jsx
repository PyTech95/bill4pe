import React, { useEffect, useState } from 'react';
import { Sparkles, AlertTriangle, Loader2 } from 'lucide-react';
import api from '@/lib/api';

/**
 * Small in-app status badge. Turns GREEN when GEMINI_API_KEY is configured on
 * the server (reads /api/health/providers -> ai.using_own_keys.gemini).
 */
export default function AIStatusBadge() {
  const [state, setState] = useState({ loading: true, ok: false });

  useEffect(() => {
    let mounted = true;
    api
      .get('/health/providers')
      .then((r) => {
        const ok = !!r?.data?.ai?.using_own_keys?.gemini;
        if (mounted) setState({ loading: false, ok });
      })
      .catch(() => {
        if (mounted) setState({ loading: false, ok: false });
      });
    return () => {
      mounted = false;
    };
  }, []);

  const { loading, ok } = state;

  return (
    <div className="flat-card p-4 flex items-center gap-3" data-testid="ai-status-card">
      <div
        className={`w-10 h-10 rounded-xl grid place-items-center shrink-0 text-white ${
          ok ? 'bg-emerald-500' : 'bg-slate-300'
        }`}
      >
        <Sparkles className="w-5 h-5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-display font-bold text-navy text-sm">Gemini AI</div>
        <div className="text-xs text-slate-500 truncate">
          Receipt scan · Voice expense · Item detection
        </div>
      </div>

      {loading ? (
        <span
          className="flex items-center gap-1.5 text-xs font-semibold text-slate-400"
          data-testid="ai-status-badge"
          data-status="checking"
        >
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Checking
        </span>
      ) : ok ? (
        <span
          className="flex items-center gap-1.5 text-xs font-bold text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-full"
          data-testid="ai-status-badge"
          data-status="connected"
        >
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          Connected
        </span>
      ) : (
        <span
          className="flex items-center gap-1.5 text-xs font-bold text-amber-600 bg-amber-50 px-2.5 py-1 rounded-full"
          data-testid="ai-status-badge"
          data-status="not-configured"
        >
          <AlertTriangle className="w-3.5 h-3.5" /> Not configured
        </span>
      )}
    </div>
  );
}
