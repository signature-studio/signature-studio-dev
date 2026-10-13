// P15: 1 instance (Memory 1 本) に M 個の OTT 処理オブジェクトを畳んだ構成を Chrome Dedicated Worker で駆動する。
// 受入条件: M=130 (上限 124〜125 本を超える plugin 数) で instantiate 失敗なし・署名 6b1696f0 一致。
//   node tools/perf/p15/chrome_shared.mjs [--m 1,4,130] [--reps 7] [--blk 1000] [--runs 3]
// 結果 = tools/perf/p15/results/chrome_shared.jsonl。Chrome は条件×反復ごとに新規起動。
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
import { startServer } from '../harness/server.mjs'; import { launchChrome } from '../harness/cdp.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../..');
const WASM = path.join(ROOT, 'ott/work/lift/ottl.wasm');
const RES = path.join(HERE, 'results'); const OUT = path.join(RES, 'chrome_shared.jsonl');
process.env.PERF_TMP ||= path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'perf'); fs.mkdirSync(process.env.PERF_TMP, { recursive: true });
if (!fs.existsSync(WASM)) { console.error(`FATAL: ${WASM} 無し (oc_artifacts: work-m6-ott が必要)`); process.exit(1); }

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const MS = arg('--m', '1,4,130').split(',').map(Number); const REPS = +arg('--reps', 7); const BLK = +arg('--blk', 1000); const RUNS = +arg('--runs', 3);

const srv = await startServer({ '/w': path.join(ROOT, 'ott/work/lift'), '/l': path.join(HERE) });
fs.mkdirSync(RES, { recursive: true });
for (let r = 0; r < RUNS; r++) for (const m of MS) {
  const b = await launchChrome({});
  try {
    const p = await b.newPage(`${srv.url}/l/web/shared_page.html`);
    const before = b.procs().filter((x) => x.type === 'renderer').reduce((a, x) => a + (x.rssMB ?? 0), 0);
    const res = await p.eval(`runShared(${JSON.stringify({ m, blk: BLK, reps: REPS })})`, { timeout: 900000 });
    const after = b.procs().filter((x) => x.type === 'renderer').reduce((a, x) => a + (x.rssMB ?? 0), 0);
    const row = { mode: 'steady_shared_memory', cfg: 'ott_shared_instance', M: m, runtime: 'chrome ' + b.version.product, cpus: os.cpus().length, cpu: os.cpus()[0]?.model ?? 'unknown', loadavg: os.loadavg().map((x) => +x.toFixed(2)), blk: BLK, reps: REPS, run: r, ...res,
      renderer_rss_mib: +after.toFixed(1), renderer_rss_delta_mib: +(after - before).toFixed(1) };
    fs.appendFileSync(OUT, JSON.stringify(row) + '\n'); console.log(JSON.stringify(row));
  } catch (e) {
    const row = { mode: 'steady_shared_memory', M: m, run: r, error: String(e).slice(0, 300) };
    fs.appendFileSync(OUT, JSON.stringify(row) + '\n'); console.log(JSON.stringify(row));
  } finally { await b.close(); }
}
await srv.close(); process.exit(0);
