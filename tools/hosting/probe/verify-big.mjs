// verify-big.mjs <baseUrl> [conc=16] [sample=0] — gen-big.mjs が作った全 chunk (d/ids.json) を取得し、sha256 先頭 128bit == id を検証する。
// sample>0 なら無作為 sample 件のみ (warm 再取得用)。ステータス分布・所要・MB/s を出す
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const ids = JSON.parse(fs.readFileSync(path.resolve(here, '../work/dist-big/d/ids.json'), 'utf8'));
const [base, conc = '16', sample = '0'] = process.argv.slice(2);
let list = ids.map((id, i) => i);
if (Number(sample) > 0) list = list.sort(() => Math.random() - 0.5).slice(0, Number(sample));
const st = {}, lat = [];
let bad = 0, bytes = 0, errors = 0, hdr = null;
const t0 = performance.now();
async function worker() {
  for (let i = list.pop(); i !== undefined; i = list.pop()) {
    const id = ids[i];
    const t1 = performance.now();
    try {
      const r = await fetch(`${base}d/c/${id.slice(0, 2)}/${id}.raw`);
      const b = Buffer.from(await r.arrayBuffer());
      st[r.status] = (st[r.status] ?? 0) + 1;
      if (!hdr) hdr = { cacheControl: r.headers.get('cache-control'), coep: r.headers.get('cross-origin-embedder-policy'), corp: r.headers.get('cross-origin-resource-policy'), cf: r.headers.get('cf-cache-status') };
      if (r.ok) {
        bytes += b.length; lat.push(performance.now() - t1);
        if (crypto.createHash('sha256').update(b).digest('hex').slice(0, 32) !== id) bad++;
      }
    } catch (e) { errors++; }
  }
}
await Promise.all(Array.from({ length: Number(conc) }, worker));
const sec = (performance.now() - t0) / 1000;
lat.sort((a, b) => a - b);
const q = (p) => Math.round(lat[Math.min(lat.length - 1, Math.floor(lat.length * p))] ?? 0);
console.log(JSON.stringify({ base, n: lat.length, statuses: st, errors, badHash: bad, GiB: +(bytes / 2 ** 30).toFixed(2), sec: +sec.toFixed(1), MBps: +(bytes / 1048576 / sec).toFixed(1), reqPerSec: +(lat.length / sec).toFixed(1), p50ms: q(0.5), p95ms: q(0.95), p99ms: q(0.99), firstHeaders: hdr }));
