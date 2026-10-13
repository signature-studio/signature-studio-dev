// P8 実 OTT 版 (Chrome): bit-exact OTT (ottl.wasm = x64c lift) を Chrome Dedicated Worker 内で
// plugin 別 instance (各自の Memory) として N 個駆動する。bench_real.mjs (node) と同一手順・同一署名。
//   node chrome_real.mjs [--n 1,4,16] [--reps 7] [--blk 1000] [--runs 3]
// 前提: tools/ott/work/lift/ottl.wasm (oc_artifacts: work-m6-ott)。結果 = tools/perf/p8/results/chrome_real.jsonl。
// glue (ottl.cjs) は node 専用 (node:fs) のため使わず、wasm の import 5 個 (env/wasi) を直接満たして instantiate する。
// Chrome は条件×反復ごとに新規起動 (NativeModule キャッシュ・RSS を持ち越さない)。
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
import { startServer } from '../../harness/server.mjs'; import { launchChrome } from '../../harness/cdp.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../../..');
const WASM = path.join(ROOT, 'ott/work/lift/ottl.wasm');
const RES = path.join(HERE, '..', 'results'); const OUT = path.join(RES, 'chrome_real.jsonl');
process.env.PERF_TMP ||= path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'perf'); fs.mkdirSync(process.env.PERF_TMP, { recursive: true });
if (!fs.existsSync(WASM)) { console.error(`FATAL: ${WASM} 無し (oc_artifacts: work-m6-ott が必要)`); process.exit(1); }

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const NS = arg('--n', '1,4,16').split(',').map(Number); const REPS = +arg('--reps', 7); const BLK = +arg('--blk', 1000); const RUNS = +arg('--runs', 3);
const LIMIT = +arg('--limit', 0);

const srv = await startServer({ '/w': path.join(ROOT, 'ott/work/lift'), '/l': HERE });
const base = srv.url;
fs.mkdirSync(RES, { recursive: true });

const procRss = async (b) => { const ps = b.procs().filter((x) => x.type === 'renderer'); return { rss: Math.max(...ps.map((x) => (x.rssMB ?? 0) * 1048576)), hwm: Math.max(...ps.map((x) => (x.hwmMB ?? 0) * 1048576)) }; };

async function one(n, limit = false) {
  const b = await launchChrome({});
  const product = 'chrome ' + b.version.product;
  try {
    const p = await b.newPage(`${base}/l/web/real_page.html`);
    const before = await procRss(b);
    const r = await p.eval(limit ? `runReal(${JSON.stringify({ limit: true, max: n })})` : `runReal(${JSON.stringify({ n, blk: BLK, reps: REPS })})`, { timeout: 900000 });
    const after = await procRss(b);
    return { mode: 'steady', cfg: 'ott_plugin_instance', N: n, runtime: product, cpus: os.cpus().length, cpu: os.cpus()[0]?.model ?? 'unknown', loadavg: os.loadavg().map((x) => +x.toFixed(2)), blk: BLK, reps: REPS, ...r,
      renderer_rss_mib: +((after.rss) / 2 ** 20).toFixed(1), renderer_rss_delta_mib: +((after.rss - before.rss) / 2 ** 20).toFixed(1), renderer_hwm_mib: +((after.hwm) / 2 ** 20).toFixed(1) };
  } finally { await b.close(); }
}

if (LIMIT) {
  for (let r = 0; r < RUNS; r++) {
    const o0 = await one(LIMIT, true); const o = { ...o0, mode: 'memory_limit' };
    fs.appendFileSync(path.join(RES, 'chrome_real_limit.jsonl'), JSON.stringify(o) + '\n'); console.log(JSON.stringify(o));
  }
  await srv.close(); process.exit(0);
}
for (let r = 0; r < RUNS; r++) for (const n of NS) {
  try {
    const o = await one(n); fs.appendFileSync(OUT, JSON.stringify(o) + '\n'); console.log(JSON.stringify(o));
  } catch (e) {
    const o = { mode: 'steady', cfg: 'ott_plugin_instance', N: n, error: String(e).slice(0, 300) };
    fs.appendFileSync(OUT, JSON.stringify(o) + '\n'); console.log(JSON.stringify(o));
  }
}
await srv.close(); process.exit(0);
