// stress.mjs <baseUrl-with-/d/> <concurrency> <total> [headerJSON] — Node fetch で chunk(1MiB) を多数 GET し、ステータス分布 (429 等)・req/s・MB/s・遅延分位を出す
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const mf = JSON.parse(fs.readFileSync(path.resolve(here, '../work/data/probe-manifest.json'), 'utf8'));
const [base, conc = '16', total = '1000', hdr = '{}'] = process.argv.slice(2);
const headers = JSON.parse(hdr);
const N = Number(total), C = Number(conc);
let next = 0, bytes = 0;
const st = {}, lat = [];
const t0 = performance.now();
async function worker() {
  for (;;) {
    const i = next++;
    if (i >= N) return;
    const c = mf.chunks[i % mf.chunks.length];
    const t1 = performance.now();
    try {
      const r = await fetch(base + c.path, { headers });
      const b = await r.arrayBuffer();
      st[r.status] = (st[r.status] ?? 0) + 1;
      if (r.ok) { bytes += b.byteLength; lat.push(performance.now() - t1); }
    } catch (e) { const k = `ERR ${e?.cause?.code ?? e?.name}`; st[k] = (st[k] ?? 0) + 1; }
  }
}
await Promise.all(Array.from({ length: C }, worker));
const sec = (performance.now() - t0) / 1000;
lat.sort((a, b) => a - b);
const q = (p) => Math.round(lat[Math.min(lat.length - 1, Math.floor(lat.length * p))] ?? 0);
console.log(JSON.stringify({ base, conc: C, total: N, statuses: st, sec: +sec.toFixed(1), reqPerSec: +(N / sec).toFixed(1), MBps: +(bytes / 1048576 / sec).toFixed(1), p50ms: q(0.5), p95ms: q(0.95), p99ms: q(0.99) }));
