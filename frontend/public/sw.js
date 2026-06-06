// BILL4PE service worker — network-first for app shell, cache-first for icons.
// Bump CACHE name whenever shell strategy changes so old SWs evict.
const CACHE = 'bill4pe-v3';
const STATIC_ASSETS = ['/manifest.json', '/icon-192.svg', '/icon-512.svg'];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(STATIC_ASSETS)).catch(() => null)
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Allow page to trigger immediate SW activation
self.addEventListener('message', (e) => {
  if (e?.data === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (e) => {
  const { request } = e;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);

  // Never touch API or cross-origin
  if (url.pathname.startsWith('/api/')) return;
  if (url.origin !== self.location.origin) return;

  const isStaticAsset =
    /\.(png|jpg|jpeg|svg|webp|ico|woff2?|ttf)$/i.test(url.pathname) ||
    url.pathname === '/manifest.json';

  if (isStaticAsset) {
    // Cache-first for true static assets
    e.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((res) => {
            if (res && res.status === 200 && res.type === 'basic') {
              const copy = res.clone();
              caches.open(CACHE).then((c) => c.put(request, copy));
            }
            return res;
          })
      )
    );
    return;
  }

  // Network-first for HTML, JS, CSS so deployments apply immediately.
  // Falls back to cache only when network is unavailable.
  e.respondWith(
    fetch(request)
      .then((res) => {
        if (res && res.status === 200 && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(request, copy));
        }
        return res;
      })
      .catch(() => caches.match(request))
  );
});
