// 案 A: R2 バインディング直配 Worker。
//  - GET/HEAD/Range/If-None-Match を R2 の range/onlyIf に委譲 (obj.range から 206 + Content-Range を組み立てる)
//  - 全レスポンスに COOP/COEP/CORP を付与 (HTML/JS/Worker/wasm/data すべて同一オリジン)
//  - 本体は obj.body をそのままストリーム (Worker メモリに載せない => CPU ほぼ 0、サイズ上限なし)
const ISOLATION = {
  'Cross-Origin-Opener-Policy': 'same-origin',
  'Cross-Origin-Embedder-Policy': 'require-corp',
  'Cross-Origin-Resource-Policy': 'same-origin',
  'X-Content-Type-Options': 'nosniff',
};

const TYPES = { html: 'text/html; charset=utf-8', js: 'text/javascript; charset=utf-8', json: 'application/json', wasm: 'application/wasm', png: 'image/png' };

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('method not allowed', { status: 405, headers: ISOLATION });
    let key = decodeURIComponent(url.pathname.slice(1));
    if (key === '' || key.endsWith('/')) key += 'index.html';

    const h = new Headers(ISOLATION);
    let obj;
    try {
      obj = request.method === 'HEAD'
        ? await env.BUCKET.head(key)
        : await env.BUCKET.get(key, { range: request.headers, onlyIf: request.headers });
    } catch (e) {
      // 範囲外 Range 等 (R2 error 10039)
      h.set('Content-Range', '*/*');
      return new Response('range not satisfiable', { status: 416, headers: h });
    }
    if (!obj) return new Response('not found', { status: 404, headers: h });

    obj.writeHttpMetadata(h);
    if (!h.has('content-type')) h.set('content-type', TYPES[key.split('.').pop()] ?? 'application/octet-stream');
    h.set('etag', obj.httpEtag);
    h.set('accept-ranges', 'bytes');
    if (key.startsWith('d/c/')) h.set('cache-control', 'public, max-age=31536000, immutable');

    if (request.method === 'HEAD') {
      h.set('content-length', String(obj.size));
      return new Response(null, { status: 200, headers: h });
    }
    if (!('body' in obj)) {
      // onlyIf (If-None-Match / If-Modified-Since) が不成立 => 304
      return new Response(null, { status: 304, headers: h });
    }
    let status = 200;
    // R2 は Range ヘッダが無くても obj.range を埋めるため、リクエストに Range がある時だけ 206 にする
    if (obj.range && request.headers.has('range')) {
      const r = obj.range; // { offset, length } | { offset } | { suffix }
      const off = r.offset ?? Math.max(0, obj.size - r.suffix);
      const len = r.length ?? obj.size - off;
      h.set('content-range', `bytes ${off}-${off + len - 1}/${obj.size}`);
      h.set('content-length', String(len));
      status = 206;
    } else {
      h.set('content-length', String(obj.size));
    }
    return new Response(obj.body, { status, headers: h });
  },
};
