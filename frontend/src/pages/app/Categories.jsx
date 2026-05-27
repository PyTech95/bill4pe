import React from 'react';
import { useNavigate } from 'react-router-dom';
import { CATEGORIES } from '@/lib/categories';
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
        {CATEGORIES.map(({ key, label, icon: Icon }) => (
          <motion.button
            key={key}
            variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
            onClick={() => nav(`/app/category/${key}`)}
            data-testid={`cat-${key}-card`}
            className="press-down flat-card p-5 text-left hover:border-navy transition"
          >
            <div className="w-10 h-10 rounded-xl bg-navy text-lime grid place-items-center">
              <Icon className="w-5 h-5" />
            </div>
            <div className="font-display font-semibold mt-3 text-navy">{label}</div>
          </motion.button>
        ))}
      </motion.div>
    </div>
  );
}
