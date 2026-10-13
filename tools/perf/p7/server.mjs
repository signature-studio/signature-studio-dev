// P7 用サーバ: 合成 wasm の動的生成 (/wasm)・静的配信 (/web)・結果受信 (POST /result)。ブラウザ非依存 (driver 不要)。
//   /wasm?c=small|mid|large&salt=N[&cc=immutable]   salt = 末尾 custom section で bytes を変える (エンジン内キャッシュ回避)
//   /wasm?c=funcs&n=N     関数 N 個 (total) の wasm        /wasm?c=bytes&d=0|1   1 GiB (+d) の wasm
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { genWasm } from '../loader/gen_wasm.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const SIZES = {
  small: { stages: 64 },
  mid: { stages: 500, nops: 100, filler: 30000 },
  large: { stages: 1000, nops: 200, filler: 90000, pad: 32 * 1024 * 1024 },
};
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript' };
const uleb = (n) => { const o = []; do { let b = n & 0x7f; n >>>= 7; if (n) b |= 0x80; o.push(b); } while (n); return o; };
const withSalt = (buf, salt) => {
  const nm = Buffer.from('salt'); const payload = Buffer.from(String(salt));
  const body = Buffer.concat([Buffer.from(uleb(nm.length)), nm, payload]);
  return Buffer.concat([buf, Buffer.from([0, ...uleb(body.length)]), body]);
};
const cache = new Map();
export function wasmFor(c, salt = 0) {
  const k = `${c}:${salt}`;
  if (!cache.has(k)) cache.set(k, withSalt(genWasm(SIZES[c]), salt));
  if (cache.size > 24) cache.delete(cache.keys().next().value);
  return cache.get(k);
}
// 関数数 n (ws_* の 3 個を含む total) の wasm: stages=0, filler = n-3
export const funcsWasm = (n) => genWasm({ stages: 0, filler: n - 3 });
// ちょうど target バイトの wasm (custom section "pad" で埋める)
export const bytesWasm = (target) => genWasm({ stages: 0, pad: target });

export function startServer() {
  const results = {};   // cfg → { key → obj }
  const logs = [];
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    const cors = { 'Cache-Control': 'no-store' };
    if (req.method === 'POST' && u.pathname === '/result') {
      let b = ''; req.on('data', (d) => { b += d; }); req.on('end', () => {
        let obj; try { obj = JSON.parse(b); } catch { obj = { raw: b.slice(0, 200) }; }
        const cfg = u.searchParams.get('cfg'), key = u.searchParams.get('key');
        if (key === 'log') logs.push({ cfg, ...obj }); else (results[cfg] ??= {})[key] = obj;
        res.writeHead(200, cors); res.end('ok');
      }); return;
    }
    if (u.pathname === '/wasm') {
      const c = u.searchParams.get('c'); let buf;
      try {
        if (c === 'funcs') buf = funcsWasm(+u.searchParams.get('n'));
        else if (c === 'bytes') buf = bytesWasm(1073741824 + (+u.searchParams.get('d') || 0));
        else buf = wasmFor(c, +(u.searchParams.get('salt') || 0));
      } catch (e) { res.writeHead(500); res.end(String(e)); return; }
      const cc = u.searchParams.get('cc') === 'immutable' ? 'public, max-age=31536000, immutable' : 'no-store';
      res.writeHead(200, { 'Content-Type': 'application/wasm', 'Content-Length': buf.length, 'Cache-Control': cc });
      res.end(buf); return;
    }
    const file = path.join(HERE, 'web', u.pathname === '/' ? 'p7.html' : u.pathname.replace(/^\/+/, ''));
    if (!file.startsWith(path.join(HERE, 'web')) || !fs.existsSync(file)) { res.writeHead(404); res.end('nf'); return; }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream', ...cors });
    res.end(fs.readFileSync(file));
  });
  return new Promise((resolve) => srv.listen(0, '127.0.0.1', () => resolve({ port: srv.address().port, url: `http://127.0.0.1:${srv.address().port}`, results, logs, close: () => srv.close() })));
}
