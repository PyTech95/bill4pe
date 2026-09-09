import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Download, X, Smartphone } from 'lucide-react';

const DISMISS_KEY = 'bill4pe_pwa_install_dismissed';
const DISMISS_DAYS = 7;

const isStandalone = () => {
  if (typeof window === 'undefined') return false;
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  );
};

const dismissedRecently = () => {
  try {
    const ts = parseInt(localStorage.getItem(DISMISS_KEY) || '0', 10);
    if (!ts) return false;
    return Date.now() - ts < DISMISS_DAYS * 24 * 60 * 60 * 1000;
  } catch { return false; }
};

export const PWAInstallBanner = () => {
  const [deferred, setDeferred] = useState(null);
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (isStandalone() || dismissedRecently()) return;

    const onPrompt = (e) => {
      e.preventDefault();
      setDeferred(e);
      setShow(true);
    };
    window.addEventListener('beforeinstallprompt', onPrompt);
    return () => window.removeEventListener('beforeinstallprompt', onPrompt);
  }, []);

  const install = async () => {
    if (!deferred) return;
    try {
      deferred.prompt();
      await deferred.userChoice;
    } catch { /* */ }
    setShow(false);
    setDeferred(null);
  };

  const dismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch { /* */ }
    setShow(false);
  };

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 30 }}
          transition={{ type: 'spring', stiffness: 220, damping: 22 }}
          className="fixed bottom-20 left-3 right-3 z-[55] max-w-screen-sm mx-auto"
          data-testid="pwa-install-banner"
        >
          <div className="relative rounded-2xl bg-navy text-white p-3 pr-12 shadow-2xl shadow-black/30 border border-white/5 flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-lime text-navy grid place-items-center shrink-0">
              <Smartphone className="w-5 h-5" strokeWidth={2} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-[0.2em] text-lime font-bold">
                Install BILL4PE
              </div>
              <div className="text-sm font-semibold leading-tight mt-0.5">
                Faster access, works offline
              </div>
            </div>
            <button
              onClick={install}
              data-testid="pwa-install-btn"
              className="press-down shrink-0 inline-flex items-center gap-1 h-9 px-3 bg-brand hover:bg-[#1858CC] rounded-full text-white text-xs font-bold"
            >
              <Download className="w-3.5 h-3.5" /> Install
            </button>
            <button
              onClick={dismiss}
              data-testid="pwa-install-dismiss-btn"
              className="absolute top-1.5 right-1.5 w-6 h-6 grid place-items-center text-white/50 hover:text-white"
              aria-label="Dismiss"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default PWAInstallBanner;
