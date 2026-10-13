// P15: Memory 本数上限は renderer プロセス単位か (Worker 単位か / Chrome 全体か) を切り分ける。
// 同一 Chrome 内で、origin 違い (localhost / 127.0.0.1 = 別 site → 別 renderer) の 2 ページで Worker を同時に立てる。
// iframe 経由は COEP (require-corp) で別 origin がブロックされるため使わない。
//   node tools/perf/p15/probe_iso.mjs [--k1 1] [--k2 1] [--max 160] [--runs 2]
// 結果 = tools/perf/p15/results/probe_iso.jsonl。前提: tools/ott/work/lift/ottl.wasm (oc_artifacts: work-m6-ott)。
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
import { startServer } from '../harness/server.mjs'; import { launchChrome } from '../harness/cdp.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../..');
const WASM = path.join(ROOT, 'ott/work/lift/ottl.wasm');
const RES = path.join(HERE, 'results'); const OUT = path.join(RES, 'probe_iso.jsonl');
process.env.PERF_TMP ||= path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'perf'); fs.mkdirSync(process.env.PERF_TMP, { recursive: true });
if (!fs.existsSync(WASM)) { console.error(`FATAL: ${WASM} 無し (oc_artifacts: work-m6-ott が必要)`); process.exit(1); }

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const K1 = +arg('--k1', 1), K2 = +arg('--k2', 1), MAX = +arg('--max', 160), RUNS = +arg('--runs', 2);

const srv = await startServer({ '/w': path.join(ROOT, 'ott/work/lift'), '/l': path.join(HERE) });
const urlA = srv.url.replace('127.0.0.1', 'localhost') + '/l/web/page.html';
const urlB = srv.url + '/l/web/page.html';
fs.mkdirSync(RES, { recursive: true });
for (let r = 0; r < RUNS; r++) {
  const b = await launchChrome({});
  try {
    const pa = await b.newPage(urlA); const pb = await b.newPage(urlB);
    const [ra, rb] = await Promise.all([
      pa.eval(`probeWorkers(${K1}, ${MAX})`, { timeout: 900000 }),
      pb.eval(`probeWorkers(${K2}, ${MAX})`, { timeout: 900000 }),
    ]);
    const renderers = b.procs().filter((x) => x.type === 'renderer').length;
    const row = { mode: 'memory_limit_iso_site', runtime: 'chrome ' + b.version.product, cpus: os.cpus().length, loadavg: os.loadavg().map((x) => +x.toFixed(2)), run: r, renderers, origin_a: ra, origin_b: rb };
    fs.appendFileSync(OUT, JSON.stringify(row) + '\n'); console.log(JSON.stringify(row));
  } catch (e) {
    const row = { mode: 'memory_limit_iso_site', k1: K1, k2: K2, run: r, error: String(e).slice(0, 300) };
    fs.appendFileSync(OUT, JSON.stringify(row) + '\n'); console.log(JSON.stringify(row));
  } finally { await b.close(); }
}
await srv.close(); process.exit(0);
