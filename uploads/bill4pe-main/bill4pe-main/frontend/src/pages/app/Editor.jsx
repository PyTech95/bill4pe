import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, ArrowRight, Sparkles } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import api from '@/lib/api';
import { catByKey } from '@/lib/categories';

const emptyItem = () => ({ name: '', quantity: 1, unit_price: 0 });

export default function Editor() {
  const nav = useNavigate();
  const [draft, setDraft] = useState(null);
  const [items, setItems] = useState([]);
  const [suggestions, setSuggestions] = useState({});

  useEffect(() => {
    try {
      const d = JSON.parse(sessionStorage.getItem('bill4pe_draft') || 'null');
      if (!d) { nav('/app'); return; }
      setDraft(d);
      setItems(d.items.length ? d.items : [emptyItem()]);
    } catch { nav('/app'); }
  }, [nav]);

  const total = useMemo(
    () => items.reduce((s, i) => s + Number(i.quantity || 0) * Number(i.unit_price || 0), 0),
    [items]
  );

  const update = (idx, patch) => setItems((arr) => arr.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  const remove = (idx) => setItems((arr) => arr.filter((_, i) => i !== idx));
  const add = () => setItems((arr) => [...arr, emptyItem()]);

  const suggest = async (idx, query) => {
    if (query.length < 2) { setSuggestions((s) => ({ ...s, [idx]: [] })); return; }
    try {
      const { data } = await api.post('/ai/suggest-items', { category: draft?.category, query });
      setSuggestions((s) => ({ ...s, [idx]: data?.suggestions || [] }));
    } catch { /* ignore */ }
  };

  const proceed = () => {
    const cleaned = items
      .filter((i) => i.name?.trim() && Number(i.quantity) > 0)
      .map((i) => ({ name: i.name.trim(), quantity: Number(i.quantity), unit_price: Number(i.unit_price) || 0 }));
    if (!cleaned.length) { toast.error('Add at least one item'); return; }
    if (total <= 0) { toast.error('Total must be greater than 0'); return; }
    sessionStorage.setItem('bill4pe_draft', JSON.stringify({ ...draft, items: cleaned }));
    nav('/app/pay');
  };

  if (!draft) return null;
  const c = catByKey(draft.category);

  return (
    <div className="pb-32">
      <div>
        <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold">
          {c?.label} / {draft.sub_category}
        </div>
        <div className="flex items-center gap-2 mt-1">
          <h1 className="font-display text-2xl font-bold text-navy">Review items</h1>
          <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider bg-lime text-navy px-2 py-0.5 rounded-full font-bold">
            <Sparkles className="w-3 h-3" /> AI
          </span>
        </div>
      </div>

      <div className="mt-5 space-y-3">
        {items.map((it, idx) => (
          <div key={idx} className="flat-card p-4" data-testid={`item-row-${idx}`}>
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <Input
                  placeholder="Item name"
                  value={it.name}
                  onChange={(e) => { update(idx, { name: e.target.value }); suggest(idx, e.target.value); }}
                  className="h-11 rounded-lg border-soft"
                  data-testid={`item-name-input-${idx}`}
                />
                {suggestions[idx]?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {suggestions[idx].map((s) => (
                      <button
                        key={s}
                        onClick={() => { update(idx, { name: s }); setSuggestions((x) => ({ ...x, [idx]: [] })); }}
                        className="text-xs px-2 py-1 rounded-full bg-[#0A1128]/5 text-navy hover:bg-lime hover:text-navy press-down"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button
                onClick={() => remove(idx)}
                data-testid={`item-remove-${idx}`}
                className="press-down p-2 rounded-lg text-slate-400 hover:text-red-500"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2 mt-2.5">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Qty</label>
                <Input
                  type="number" min="0" step="1" value={it.quantity}
                  onChange={(e) => update(idx, { quantity: e.target.value })}
                  className="h-10 mt-1 font-mono rounded-lg border-soft"
                  data-testid={`item-qty-${idx}`}
                />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Price ₹</label>
                <Input
                  type="number" min="0" step="0.01" value={it.unit_price}
                  onChange={(e) => update(idx, { unit_price: e.target.value })}
                  className="h-10 mt-1 font-mono rounded-lg border-soft"
                  data-testid={`item-price-${idx}`}
                />
              </div>
            </div>
            <div className="mt-2.5 text-right font-mono text-sm text-slate-500">
              = ₹ {(Number(it.quantity || 0) * Number(it.unit_price || 0)).toFixed(2)}
            </div>
          </div>
        ))}

        <button
          onClick={add}
          data-testid="add-item-btn"
          className="press-down w-full border-2 border-dashed border-soft rounded-2xl py-4 flex items-center justify-center gap-2 text-slate-500 hover:border-navy hover:text-navy"
        >
          <Plus className="w-4 h-4" /> Add item
        </button>
      </div>

      {/* Sticky total bar */}
      <div className="fixed bottom-14 left-0 right-0 z-20 backdrop-blur-xl bg-white/95 border-t border-soft">
        <div className="max-w-screen-sm mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 font-semibold">Total</div>
            <div className="font-mono text-2xl font-bold text-navy" data-testid="editor-total">₹ {total.toFixed(2)}</div>
          </div>
          <Button
            onClick={proceed}
            disabled={total <= 0}
            className="press-down h-12 px-6 bg-brand text-white hover:bg-[#1858CC] rounded-full font-semibold"
            data-testid="proceed-to-pay-btn"
          >
            Pay Now <ArrowRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      </div>
    </div>
  );
}
