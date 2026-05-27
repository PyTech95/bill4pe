import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { catByKey } from '@/lib/categories';
import { ChevronRight } from 'lucide-react';
import { motion } from 'framer-motion';

export default function SubCategory() {
  const { cat } = useParams();
  const nav = useNavigate();
  const c = catByKey(cat);
  if (!c) return <div>Unknown category.</div>;
  const Icon = c.icon;
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-4">
        <div className="w-12 h-12 rounded-2xl bg-navy text-brand grid place-items-center">
          <Icon className="w-6 h-6" />
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Category</div>
          <h1 className="font-display text-2xl font-bold text-navy">{c.label}</h1>
        </div>
      </div>

      <div>
        <div className="text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold mt-4">Pick sub-category</div>
        <motion.div
          initial="hidden" animate="show"
          variants={{ show: { transition: { staggerChildren: 0.04 } } }}
          className="mt-3 space-y-2.5"
        >
          {c.sub.map((s) => (
            <motion.button
              key={s}
              variants={{ hidden: { opacity: 0, x: -8 }, show: { opacity: 1, x: 0 } }}
              onClick={() => nav(`/app/capture/${cat}/${encodeURIComponent(s)}`)}
              data-testid={`subcat-${s.toLowerCase()}-btn`}
              className="press-down w-full flat-card p-4 flex items-center justify-between hover:border-navy"
            >
              <span className="font-semibold text-navy">{s}</span>
              <ChevronRight className="w-5 h-5 text-slate-300" />
            </motion.button>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
