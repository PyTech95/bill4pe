import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

/**
 * Shared layout for static legal/policy pages (Privacy, Terms, etc.).
 * Renders a clean reading column with a "Back to home" link and a navy footer strip.
 */
export default function LegalLayout({ title, updatedOn, children }) {
  useEffect(() => { document.title = `${title} · BILL4PE`; }, [title]);
  return (
    <div className="min-h-screen bg-white text-navy flex flex-col">
      {/* Top bar */}
      <header className="border-b border-soft">
        <div className="max-w-3xl mx-auto px-5 md:px-8 h-16 flex items-center justify-between">
          <Link to="/" className="bg-white inline-flex items-center p-1.5 rounded-lg border border-soft">
            <img src="/logo.png" alt="Bill4Pe — The Intelligent Building" className="h-12 w-auto object-contain" />
          </Link>
          <Link
            to="/"
            data-testid="legal-back-btn"
            className="press-down inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-semibold text-slate-500 hover:text-navy hover:bg-slate-100"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back to home
          </Link>
        </div>
      </header>

      {/* Body */}
      <main className="flex-1">
        <article className="max-w-3xl mx-auto px-5 md:px-8 py-14 md:py-20">
          <div className="text-[11px] uppercase tracking-[0.3em] font-bold text-slate-400">
            Legal
          </div>
          <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tight mt-3">
            {title}
          </h1>
          {updatedOn && (
            <div className="mt-3 text-sm text-slate-500">Last updated: {updatedOn}</div>
          )}
          <div className="prose-content mt-10 leading-relaxed text-[15px] text-slate-700">
            {children}
          </div>
        </article>
      </main>

      {/* Footer */}
      <footer className="bg-navy text-white px-5 md:px-8 py-10">
        <div className="max-w-3xl mx-auto flex flex-wrap items-center justify-between gap-4 text-sm">
          <div className="text-white/50">© 2026 BILL4PE · www.bill4pe.com</div>
          <div className="flex gap-5 text-white/70">
            <Link to="/privacy" className="hover:text-brand">Privacy</Link>
            <Link to="/terms" className="hover:text-brand">Terms</Link>
            <Link to="/contact" className="hover:text-brand">Contact</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

/* Common style helpers used inside the children */
export const H2 = ({ children }) => (
  <h2 className="font-display font-bold text-2xl text-navy mt-10 mb-3 tracking-tight">{children}</h2>
);
export const H3 = ({ children }) => (
  <h3 className="font-display font-bold text-lg text-navy mt-6 mb-2">{children}</h3>
);
export const P = ({ children }) => (
  <p className="mt-3 text-slate-600 leading-relaxed">{children}</p>
);
export const UL = ({ children }) => (
  <ul className="mt-3 space-y-2 list-disc pl-6 text-slate-600 marker:text-brand">{children}</ul>
);
