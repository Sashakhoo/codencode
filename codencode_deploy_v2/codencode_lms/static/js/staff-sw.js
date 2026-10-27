/* Staff Portal service worker: served at /staff/sw.js with scope /staff/.
   Shows Web Push notifications; no offline caching (records must be live). */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('push', e => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (_) { data = {body: e.data && e.data.text()}; }
  e.waitUntil(self.registration.showNotification(data.title || 'Codencode Staff', {
    body: data.body || '',
    icon: '/static/img/favicon-192.png',
    badge: '/static/img/favicon-32.png',
    data: {url: data.url || '/staff'},
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = new URL(e.notification.data && e.notification.data.url || '/staff', self.location.origin).href;
  e.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(list => {
    for (const c of list) if (c.url.startsWith(self.location.origin + '/staff') && 'focus' in c) { c.navigate(url); return c.focus(); }
    return self.clients.openWindow(url);
  }));
});

self.addEventListener('fetch', () => {});
