import React from 'react';
import { useNavigate } from 'react-router-dom';
import { CATEGORIES } from '@/lib/categories';
import { ChevronRight } from 'lucide-react';
import { motion } from 'framer-motion';

export default function Categories() {
  const nav = useNavigate();
  return (
    <div>
      <h1 className="font-display text-2xl font-bold text-navy">All categories</h1>
      <p className="text-sm text-slate-500 mt-1">Pick any service to start.</p>
      <motion.div
        initial="hidden" animate="show"
        variants={{ show: { transition: { staggerChildren: 0.03 } } }}
        className="grid grid-cols-2 gap-3 mt-6"
      >
        {CATEGORIES.map(({ key, label, icon: Icon, sub }) => (
          <motion.button
            key={key}
            variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
            onClick={() => nav(`/app/category/${key}`)}
            data-testid={`cat-${key}-card`}
            className="press-down group flat-card p-3 text-left hover:border-navy transition-colors flex items-center gap-3"
          >
            <div className="w-11 h-11 rounded-xl bg-navy text-white grid place-items-center shrink-0 group-hover:bg-brand group-hover:text-white transition-colors">
              <Icon className="w-5 h-5" strokeWidth={1.8} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-display font-bold text-sm text-navy truncate">{label}</div>
              <div className="text-[10px] text-slate-400 font-medium mt-0.5">{sub.length} options</div>
            </div>
            <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-navy transition shrink-0" />
          </motion.button>
        ))}
      </motion.div>
    </div>
  );
}
