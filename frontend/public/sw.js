// Offline-first service worker.
//
// A screening camp in a village has no reliable connectivity. The app shell
// and its audio assets are cached on first visit, so the audiogram entry,
// the simulator, the screening test and the charts all keep working with
// the network gone. API calls are network-first (they need the backend),
// but a cached response is served if the request fails.

// Bump this on any change to the caching strategy — it drops old caches.
const CACHE = 'audiosense-v2'
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icon.svg',
  '/audio/speech_sample.wav']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((c) => Promise.allSettled(SHELL.map((u) => c.add(u))))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  // API: fresh data preferred, cached copy as a fallback when offline.
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone()
          caches.open(CACHE).then((c) => c.put(request, copy))
          return res
        })
        .catch(() => caches.match(request)),
    )
    return
  }

  // Navigations go to the network first. Serving the app shell from cache
  // would keep showing yesterday's build after a deploy; falling back to the
  // cache only when the network fails preserves offline use.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone()
          caches.open(CACHE).then((c) => c.put(request, copy))
          return res
        })
        .catch(() => caches.match(request).then((c) => c || caches.match('/index.html'))),
    )
    return
  }

  // Hashed assets: cache first, revalidate in the background.
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((res) => {
          const copy = res.clone()
          caches.open(CACHE).then((c) => c.put(request, copy))
          return res
        })
        .catch(() => cached || caches.match('/index.html'))
      return cached || network
    }),
  )
})
