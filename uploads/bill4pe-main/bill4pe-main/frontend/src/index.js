import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { initNative, isNative } from "@/lib/native";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// Initialize native (Capacitor) features when running inside the Android/iOS shell.
initNative();

// Register PWA service worker (web only). Skipped inside the native app shell,
// where a service worker can interfere with the bundled capacitor:// assets.
if ('serviceWorker' in navigator && !isNative()) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').then((reg) => {
      const promptUpdate = (worker) => {
        if (!worker) return;
        worker.addEventListener('statechange', () => {
          if (worker.state === 'installed' && navigator.serviceWorker.controller) {
            worker.postMessage('SKIP_WAITING');
          }
        });
      };
      if (reg.waiting) reg.waiting.postMessage('SKIP_WAITING');
      reg.addEventListener('updatefound', () => promptUpdate(reg.installing));
      // Check for updates every time the page is shown (also covers bfcache restore on iOS)
      window.addEventListener('pageshow', () => { try { reg.update(); } catch { /* noop */ } });
    }).catch(() => {});

    let reloaded = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (reloaded) return;
      reloaded = true;
      window.location.reload();
    });
  });
}
