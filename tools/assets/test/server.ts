// テスト/開発用の静的 chunk サーバ。R2 カスタムドメイン+Transform Rules 構成を模す:
//   - c/*.br -> Content-Encoding: br, c/*.zst -> zstd, m/*.json -> br, Cache-Control: immutable
//   - COOP/COEP (SAB 用) + CORP: cross-origin、CORS
//   - Range 対応 (raw 本体のみ。Content-Encoding 付きは Range 不可: 仕様どおり)
//   - 遅延/帯域シェーピング: latencyMs (TTFB 加算) / mbps (レスポンス帯域上限, 接続毎)
//   - /__stats (リクエスト数/バイト数), /__reset, /__report (ブラウザテスト結果受信)
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

export interface ServerOptions {
  root: string;
  port?: number;
  latencyMs?: number;
  mbps?: number;
  /** /app/* で配信する静的ディレクトリ (ブラウザテスト用 bundle/html) */
  appDir?: string;
}

export interface TestServer {
  port: number;
  url: string;
  stats(): { requests: number; bytes: number; byKind: Record<string, number> };
  reset(): void;
  setShaping(latencyMs: number, mbps: number): void;
  waitReport(timeoutMs: number): Promise<any>;
  close(): Promise<void>;
}

const MIME: Record<string, string> = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.map': 'application/json' };

export function startServer(o: ServerOptions): Promise<TestServer> {
  let latency = o.latencyMs ?? 0;
  let mbps = o.mbps ?? 0;
  let requests = 0;
  let bytes = 0;
  let byKind: Record<string, number> = {};
  let linkFree = 0;
  let netOff = false;
  let reportResolve: ((v: any) => void) | null = null;
  let pendingReport: any = undefined;

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  const server = http.createServer(async (req, res) => {
    const u = new URL(req.url ?? '/', 'http://x');
    const common = {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
      'Cross-Origin-Resource-Policy': 'cross-origin',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Expose-Headers': 'Content-Length, Content-Range, Content-Encoding',
    };
    if (req.method === 'OPTIONS') {
      res.writeHead(204, { ...common, 'Access-Control-Allow-Headers': '*' });
      return res.end();
    }
    if (u.pathname === '/__stats') {
      res.writeHead(200, { ...common, 'content-type': 'application/json' });
      return res.end(JSON.stringify({ requests, bytes, byKind }));
    }
    if (u.pathname === '/__shape') {
      latency = Number(u.searchParams.get('latency') ?? latency);
      mbps = Number(u.searchParams.get('mbps') ?? mbps);
      res.writeHead(200, common);
      return res.end('ok');
    }
    if (u.pathname === '/__reset') {
      requests = 0;
      bytes = 0;
      byKind = {};
      res.writeHead(200, common);
      return res.end('ok');
    }
    if (u.pathname === '/__report' && req.method === 'GET') {
      // ?wait=<ms>: ロングポール。到着まで 1 本の要求で待つ (250ms ポーリングの反复 GET が
      // pendingReport を「消費」して本体の受信が空になる競合を避ける。curl デバッグでも消費しない)
      const waitMs = Number(u.searchParams.get('wait') ?? 0);
      if (pendingReport !== undefined) {
        const v = pendingReport;
        pendingReport = undefined;
        res.writeHead(200, { ...common, 'content-type': 'application/json' });
        return res.end(JSON.stringify(v));
      }
      if (waitMs <= 0) {
        res.writeHead(204, common);
        return res.end();
      }
      const timer = setTimeout(() => {
        reportResolve = null;
        res.writeHead(204, common);
        res.end();
      }, waitMs);
      reportResolve = (v) => {
        clearTimeout(timer);
        reportResolve = null;
        res.writeHead(200, { ...common, 'content-type': 'application/json' });
        res.end(JSON.stringify(v));
      };
      return;
    }
    if (u.pathname === '/__net') {
      // chunk (c/) の取得を遮断 (キャッシュヒット実証用)。manifest/latest は通す
      // (266KB 級の内容アドレス manifest は毎回取得が前提。遮断対象は 314MB 級の本体 chunk)。
      netOff = u.searchParams.get('mode') !== 'on';
      res.writeHead(200, common);
      return res.end(netOff ? 'net off' : 'net on');
    }
    if (u.pathname === '/__report' && req.method === 'POST') {
      const chunks: Buffer[] = [];
      for await (const c of req) chunks.push(c as Buffer);
      const v = JSON.parse(Buffer.concat(chunks).toString());
      if (reportResolve) reportResolve(v);
      else pendingReport = v;
      res.writeHead(200, common);
      return res.end('ok');
    }
    let file: string;
    let ct = 'application/octet-stream';
    const headers: Record<string, string | number> = { ...common };
    let kind = 'other';
    if (u.pathname.startsWith('/app/') && o.appDir) {
      file = path.join(o.appDir, u.pathname.slice(5) || 'index.html');
      ct = MIME[path.extname(file)] ?? ct;
      kind = 'app';
    } else {
      if (netOff && u.pathname.startsWith('/c/')) {
        res.writeHead(503, { ...common, 'content-type': 'text/plain' });
        return res.end('net off (c/m blocked)');
      }
      const rel = decodeURIComponent(u.pathname).replace(/^\/+/, '');
      file = path.join(o.root, rel);
      if (!file.startsWith(o.root)) {
        res.writeHead(403, common);
        return res.end();
      }
      if (rel.startsWith('c/')) {
        kind = 'chunk';
        if (rel.endsWith('.br')) headers['Content-Encoding'] = 'br';
        else if (rel.endsWith('.zst')) headers['Content-Encoding'] = 'zstd';
        headers['Cache-Control'] = 'public, max-age=31536000, immutable';
      } else if (rel.startsWith('m/')) {
        kind = 'manifest';
        ct = 'application/json';
        headers['Content-Encoding'] = 'br';
        headers['Cache-Control'] = 'public, max-age=31536000, immutable';
      } else if (rel === 'latest.json') {
        kind = 'latest';
        ct = 'application/json';
        headers['Cache-Control'] = 'public, max-age=60';
      }
    }
    let st: fs.Stats;
    try {
      st = fs.statSync(file);
      if (!st.isFile()) throw new Error('nf');
    } catch {
      res.writeHead(404, common);
      return res.end('not found');
    }
    requests++;
    byKind[kind] = (byKind[kind] ?? 0) + 1;
    if (latency > 0) await sleep(latency);
    let start = 0;
    let end = st.size - 1;
    let status = 200;
    const range = req.headers.range;
    if (range && !headers['Content-Encoding']) {
      const m = /bytes=(\d*)-(\d*)/.exec(range);
      if (m) {
        if (m[1] === '') start = Math.max(0, st.size - Number(m[2]));
        else {
          start = Number(m[1]);
          if (m[2]) end = Math.min(end, Number(m[2]));
        }
        status = 206;
        headers['Content-Range'] = `bytes ${start}-${end}/${st.size}`;
      }
    }
    headers['Content-Type'] = ct;
    headers['Content-Length'] = end - start + 1;
    headers['Accept-Ranges'] = headers['Content-Encoding'] ? 'none' : 'bytes';
    res.writeHead(status, headers);
    const body = fs.readFileSync(file).subarray(start, end + 1);
    bytes += body.length;
    if (mbps > 0) {
      // 帯域は全接続で共有 (単一リンク模擬): 共有タイムラインに各 slice の送出時間を予約する
      const slice = 64 * 1024;
      const perMs = (mbps * 1e6) / 8 / 1000;
      for (let off = 0; off < body.length; off += slice) {
        const part = body.subarray(off, off + slice);
        const sliceMs = part.length / perMs;
        const now = performance.now();
        const startAt = Math.max(now, linkFree);
        linkFree = startAt + sliceMs;
        await sleep(startAt + sliceMs - now);
        res.write(part);
      }
      res.end();
    } else res.end(body);
  });

  return new Promise((resolve) => {
    server.listen(o.port ?? 0, '127.0.0.1', () => {
      const port = (server.address() as { port: number }).port;
      resolve({
        port,
        url: `http://127.0.0.1:${port}`,
        stats: () => ({ requests, bytes, byKind: { ...byKind } }),
        reset: () => {
          requests = 0;
          bytes = 0;
          byKind = {};
        },
        setShaping: (l, m) => {
          latency = l;
          mbps = m;
        },
        waitReport: (ms) =>
          new Promise((res, rej) => {
            if (pendingReport !== undefined) {
              const v = pendingReport;
              pendingReport = undefined;
              return res(v);
            }
            const t = setTimeout(() => rej(new Error('report timeout')), ms);
            reportResolve = (v) => {
              clearTimeout(t);
              reportResolve = null;
              res(v);
            };
          }),
        close: () => new Promise<void>((r) => (server.closeAllConnections(), server.close(() => r()))),
      });
    });
  });
}

// CLI: node test/server.ts <root> [--port N] [--latency MS] [--mbps N]
if (import.meta.url === `file://${process.argv[1]}`) {
  const a = process.argv.slice(2);
  const get = (k: string, d?: string) => (a.includes(k) ? a[a.indexOf(k) + 1] : d);
  const s = await startServer({ root: path.resolve(a[0]), port: Number(get('--port', '8787')), latencyMs: Number(get('--latency', '0')), mbps: Number(get('--mbps', '0')), appDir: get('--appdir') ? path.resolve(get('--appdir')!) : undefined });
  console.log('serving', a[0], 'at', s.url);
}
