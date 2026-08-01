// Kill switch for the service worker shipped with the 2021 Create React App
// build. Returning visitors still hold that worker; this replacement claims
// their clients, purges every cache it left behind, unregisters itself and
// reloads the page once so the fresh site is served.
//
// This file must keep its path. Browsers re-fetch the worker they already have
// registered, and that fetch is the only chance to hand them code that removes
// it. Deleting the file instead would leave the 2021 worker in place.

self.addEventListener('install', function () {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    (async function () {
      var names = await caches.keys();
      await Promise.all(names.map(function (name) { return caches.delete(name); }));
      await self.registration.unregister();
      var windows = await self.clients.matchAll({ type: 'window' });
      windows.forEach(function (client) { client.navigate(client.url); });
    })()
  );
});

self.addEventListener('fetch', function (event) {
  // Never serve from cache again — always go to the network.
  event.respondWith(fetch(event.request));
});
