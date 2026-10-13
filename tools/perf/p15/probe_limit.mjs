// P15: Chrome 154 で、Worker を K 個に分けたときの Memory 本数上限を測る (instance は駆動しない)。
//   node tools/perf/p15/probe_limit.mjs [--k 1,2,4] [--max 160] [--runs 2]
// 前提: tools/ott/work/lift/ottl.wasm (oc_artifacts: work-m6-ott)。結果 = tools/perf/p15/results/probe_limit.jsonl。
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
import { startServer } from '../harness/server.mjs'; import { launchChrome } from '../harness/cdp.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../..');
const WASM = path.join(ROOT, 'ott/work/lift/ottl.wasm');
const RES = path.join(HERE, 'results'); const OUT = path.join(RES, 'probe_limit.jsonl');
process.env.PERF_TMP ||= path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'perf'); fs.mkdirSync(process.env.PERF_TMP, { recursive: true });
if (!fs.existsSync(WASM)) { console.error(`FATAL: ${WASM} 無し (oc_artifacts: work-m6-ott が必要)`); process.exit(1); }

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const KS = arg('--k', '1,2,4').split(',').map(Number); const MAX = +arg('--max', 160); const RUNS = +arg('--runs', 2);

const srv = await startServer({ '/w': path.join(ROOT, 'ott/work/lift'), '/l': path.join(HERE) });
fs.mkdirSync(RES, { recursive: true });
for (let r = 0; r < RUNS; r++) for (const k of KS) {
  const b = await launchChrome({});
  try {
    const p = await b.newPage(`${srv.url}/l/web/page.html`);
    const o = await p.eval(`probeWorkers(${k}, ${MAX})`, { timeout: 900000 });
    const row = { mode: 'memory_limit_multi_worker', runtime: 'chrome ' + b.version.product, cpus: os.cpus().length, loadavg: os.loadavg().map((x) => +x.toFixed(2)), run: r, ...o };
    fs.appendFileSync(OUT, JSON.stringify(row) + '\n'); console.log(JSON.stringify(row));
  } catch (e) {
    const row = { mode: 'memory_limit_multi_worker', k, run: r, error: String(e).slice(0, 300) };
    fs.appendFileSync(OUT, JSON.stringify(row) + '\n'); console.log(JSON.stringify(row));
  } finally { await b.close(); }
}
await srv.close(); process.exit(0);
