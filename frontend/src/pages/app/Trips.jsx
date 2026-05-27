import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MapPin, Plane, Calendar, ChevronRight, Plus } from 'lucide-react';
import api from '@/lib/api';

export default function Trips() {
  const nav = useNavigate();
  const [trips, setTrips] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/expenses/trips').then(({ data }) => setTrips(data.trips || []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">Reimbursement</div>
        <h1 className="font-display text-2xl font-bold text-navy mt-1">Trip history</h1>
        <p className="text-sm text-slate-500 mt-1">Travel expenses grouped by day.</p>
      </div>

      {loading && <div className="py-10 text-center text-slate-400">Loading...</div>}

      {!loading && trips.length === 0 && (
        <div className="flat-card p-10 text-center">
          <Plane className="w-10 h-10 text-slate-300 mx-auto" strokeWidth={1.4} />
          <h3 className="font-display font-bold text-navy mt-3">No trips yet</h3>
          <p className="text-sm text-slate-500 mt-1">Add a Travel expense to start a trip.</p>
          <button
            onClick={() => nav('/app/category/travel')}
            className="press-down mt-5 inline-flex items-center gap-1.5 bg-brand text-white px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-[#1858CC]"
            data-testid="trips-empty-cta"
          >
            <Plus className="w-4 h-4" /> Log travel expense
          </button>
        </div>
      )}

      {!loading && trips.map((t) => (
        <div key={t.date} className="flat-card p-5" data-testid={`trip-${t.date}`}>
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-400 font-semibold">
                <Calendar className="w-3.5 h-3.5" /> {t.date}
              </div>
              <h3 className="font-display font-bold text-xl text-navy mt-1.5">
                {t.merchants.length === 0 ? 'Travel day' : t.merchants.slice(0, 2).join(' · ')}
                {t.merchants.length > 2 && <span className="text-slate-400"> +{t.merchants.length - 2}</span>}
              </h3>
              <div className="text-xs text-slate-500 mt-1">{t.legs} {t.legs === 1 ? 'leg' : 'legs'}</div>
            </div>
            <div className="text-right">
              <div className="text-[10px] uppercase tracking-wider text-slate-400">Total</div>
              <div className="font-mono font-bold text-navy text-lg">₹ {t.total.toFixed(2)}</div>
            </div>
          </div>

          <div className="mt-4 space-y-2 divide-y divide-soft border-t border-soft pt-3">
            {t.expenses.map((e) => (
              <button
                key={e.id}
                onClick={() => nav(`/app/bill/${e.id}`)}
                className="press-down w-full flex items-center gap-3 py-2 text-left"
                data-testid={`trip-leg-${e.id}`}
              >
                <MapPin className="w-4 h-4 text-slate-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-navy truncate">
                    {e.payment?.merchant_name || e.sub_category || 'Travel'}
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                    {e.sub_category || '—'} · {e.created_at?.slice(11, 16)}
                  </div>
                </div>
                <div className="font-mono text-sm text-navy">₹ {Number(e.total).toFixed(2)}</div>
                <ChevronRight className="w-4 h-4 text-slate-300" />
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
