// P8 ベンチ (headless Chrome の Dedicated Worker 内): node 版と同じ lib.mjs を実行する。
//   node chrome_p8.mjs steady|startup|memory [--n 1,4,16] [--reps 5] [--sfx _light] [--runs 3]
// startup / memory は条件×反復ごとに Chrome を新規起動 (NativeModule キャッシュ・RSS を持ち越さない)。
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
import { startServer } from '../harness/server.mjs'; import { launchChrome } from '../harness/cdp.mjs'; import { CONFIG_GRID } from './lib.mjs';
const HERE = path.dirname(fileURLToPath(import.meta.url)); const W = path.join(HERE, 'work'); const RES = path.join(HERE, 'results');
process.env.PERF_TMP ||= path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'perf'); fs.mkdirSync(process.env.PERF_TMP, { recursive: true });
const argv = process.argv.slice(2); const arg = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const mode = argv[0]; const NS = arg('--n', '1,4,16').split(',').map(Number); const REPS = +arg('--reps', 5); const SFX = arg('--sfx', ''); const RUNS = +arg('--runs', 1); const TARGET_MS = +arg('--target-ms', 150);
const JSFLAGS = process.env.P8_JSFLAGS || ''; const OUT = process.env.P8_OUT || path.join(RES, 'p8.jsonl'); const CFGS = arg('--cfgs', '') ? arg('--cfgs', '').split(',') : null;
const srv = await startServer({ '/w': W, '/l': HERE });
const base = srv.url;
const emit = (o) => { if (JSFLAGS) o.jsflags = JSFLAGS; fs.appendFileSync(OUT, JSON.stringify(o) + '\n'); console.log(JSON.stringify(o)); };
async function withChrome(fn) { const b = await launchChrome({ jsFlags: JSFLAGS }); try { const p = await b.newPage(`${base}/l/web/page.html`); return await fn(b, p); } finally { await b.close(); } }
const procRss = async (b) => { const ps = b.procs().filter((x) => x.type === 'renderer'); return { rss: Math.max(...ps.map((x) => (x.rssMB ?? 0) * 1048576)), hwm: Math.max(...ps.map((x) => (x.hwmMB ?? 0) * 1048576)) }; };
const run = (p, b, cfg, N, extra = {}) => p.eval(`runIt(${JSON.stringify({ mode, cfg, N, sfx: SFX, reps: REPS, targetMs: TARGET_MS, info: { runtime: 'chrome ' + b.version.product, cpus: os.cpus().length }, loadavg: os.loadavg().map((x) => +x.toFixed(2)), ...extra })})`, { timeout: 300000 });
if (mode === 'steady') {
  for (let r = 0; r < RUNS; r++) await withChrome(async (b, p) => {
    for (const N of NS) for (const cfg of CFGS ?? CONFIG_GRID.steady) { if (cfg.startsWith('static') && ![1, 4, 16].includes(N)) continue; try { emit(await run(p, b, cfg, N)); } catch (e) { emit({ mode, cfg: cfg + SFX, N, error: String(e).slice(0, 300) }); } }
  });
} else {
  for (const N of NS) for (const cfg of CONFIG_GRID[mode]) {
    if (cfg.startsWith('static') && ![1, 4, 16].includes(N)) continue;
    for (let r = 0; r < (mode === 'startup' ? Math.max(RUNS, REPS) : 1); r++) {
      try { await withChrome(async (b, p) => {
        const before = mode === 'memory' ? await procRss(b) : null; const res = await run(p, b, cfg, N);
        if (mode === 'memory') { const after = await procRss(b); res.rss_delta_bytes = after.rss - before.rss; res.hwm_bytes = after.hwm; }
        emit(res); }); } catch (e) { emit({ mode, cfg: cfg + SFX, N, error: String(e).slice(0, 300) }); }
    }
  }
}
await srv.close(); process.exit(0);
