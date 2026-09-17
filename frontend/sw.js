self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method === 'GET' && request.mode === 'navigate') {
    event.respondWith(
      fetch(request).then(async (response) => {
        if (!response.ok) return response;
        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('text/html')) return response;
        const html = await response.text();
        const fixed = html.replace(
          "(data.sources_ok||[]).map(s=>s.code+' '+s.count)",
          "(data.sources_ok||[]).filter(Boolean).map(s=>(s&&s.code||'SOURCE')+' '+(Number.isFinite(s&&s.count)?s.count:0))"
        );
        return new Response(fixed, {
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
        });
      })
    );
    return;
  }

  if (request.method !== 'POST' || url.pathname !== '/api/scan') {
    return;
  }

  event.respondWith(
    fetch(request).then(async (response) => {
      if (!response.ok) return response;

      try {
        const payload = await response.clone().json();
        payload.count = Number.isFinite(payload.count) ? payload.count : 0;
        payload.sources_ok = (Array.isArray(payload.sources_ok) ? payload.sources_ok : [])
          .filter(Boolean).map((source) => typeof source === 'string'
            ? { code: source, count: 0 }
            : { code: source.code || 'SOURCE', count: Number.isFinite(source.count) ? source.count : 0 });
        payload.sources_fail = (Array.isArray(payload.sources_fail) ? payload.sources_fail : [])
          .filter(Boolean).map((source) => typeof source === 'string'
            ? { code: source, error: 'Fuente no disponible' }
            : { code: source.code || 'SOURCE', error: source.error || 'Fuente no disponible' });
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
