// 依存なし静的サーバ。COOP/COEP 付与 (cross-origin isolated → performance.now 5us 精度, SAB 可)。
//   mounts: { '/w': '<dir>', '/h': '<dir>' }
//   ?bps=<bytes/sec> : 応答を帯域制限 (streaming compile の隠蔽効果測定用)
//   ?cc=<cache-control 値> : Cache-Control 上書き (既定 no-store)
//   ?etag=1 : 強い ETag を付与
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const MIME = { '.wasm': 'application/wasm', '.js': 'text/javascript', '.mjs': 'text/javascript', '.html': 'text/html',
  '.json': 'application/json', '.css': 'text/css' };

export function startServer(mounts, { port = 0 } = {}) {
  const stats = { requests: 0, bytes: 0, log: [] };
  const defaults = { cc: 'no-store' };
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    stats.requests++;
    let file = null;
    for (const [pre, dir] of Object.entries(mounts)) {
      if (u.pathname === pre || u.pathname.startsWith(pre + '/')) { file = path.join(dir, decodeURIComponent(u.pathname.slice(pre.length))); break; }
    }
    if (!file || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end('nf'); return; }
    const st = fs.statSync(file);
    const h = {
      'Content-Type': MIME[path.extname(file)] || 'application/octet-stream',
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
      'Cross-Origin-Resource-Policy': 'same-origin',
      'Cache-Control': u.searchParams.get('cc') || defaults.cc,
      'Content-Length': st.size,
    };
    if (u.searchParams.get('etag')) h.ETag = `"${st.size}-${st.mtimeMs}"`;
    if (req.headers['if-none-match'] && h.ETag && req.headers['if-none-match'] === h.ETag) { res.writeHead(304, h); res.end(); return; }
    stats.log.push(`${req.method} ${u.pathname}${u.search}`);
    res.writeHead(200, h);
    const bps = +(u.searchParams.get('bps') || 0);
    const rs = fs.createReadStream(file, { highWaterMark: bps ? Math.max(4096, Math.floor(bps / 100)) : 1 << 20 });
    if (!bps) { rs.on('data', (c) => { stats.bytes += c.length; }); rs.pipe(res); return; }
    // 帯域制限: 10ms 刻みで bps/100 バイトずつ送出
    rs.on('data', (c) => {
      stats.bytes += c.length;
      rs.pause();
      res.write(c, () => setTimeout(() => rs.resume(), 10));
    });
    rs.on('end', () => res.end());
  });
  return new Promise((resolve) => srv.listen(port, '127.0.0.1', () => {
    resolve({ defaults, port: srv.address().port, url: `http://127.0.0.1:${srv.address().port}`, stats, close: () => new Promise((r) => srv.close(r)) });
  }));
}
