self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== 'POST' || url.pathname !== '/api/scan') {
    return;
  }

  event.respondWith(
    fetch(request).then(async (response) => {
      if (!response.ok) return response;

      try {
        const payload = await response.clone().json();

        payload.count = Number.isFinite(payload.count) ? payload.count : 0;

        payload.sources_ok = (Array.isArray(payload.sources_ok)
          ? payload.sources_ok
          : []
        ).filter(Boolean).map((source) => {
          if (typeof source === 'string') {
            return { code: source, count: 0 };
          }
          return {
            code: source.code || 'SOURCE',
            count: Number.isFinite(source.count) ? source.count : 0,
          };
        });

        payload.sources_fail = (Array.isArray(payload.sources_fail)
          ? payload.sources_fail
          : []
        ).filter(Boolean).map((source) => {
          if (typeof source === 'string') {
            return { code: source, error: 'Fuente no disponible' };
          }
          return {
            code: source.code || 'SOURCE',
            error: source.error || 'Fuente no disponible',
          };
        });

        const headers = new Headers(response.headers);
        headers.set('content-type', 'application/json; charset=utf-8');

        return new Response(JSON.stringify(payload), {
          status: response.status,
          statusText: response.statusText,
          headers,
        });
      } catch (error) {
        return response;
      }
    })
  );
});
