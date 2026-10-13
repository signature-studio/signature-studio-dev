// P8 ベンチ (node): steady (定常 µs/block) / startup (compile+instantiate+初回) / memory (RSS) を構成別に測る。
// 使い方: node bench.mjs steady|startup|memory [--n 1,4,16] [--reps 5] [--sfx _light] [--runs 3] ; 子プロセス: --one <mode> <cfg> <N>
import fs from 'node:fs'; import path from 'node:path'; import os from 'node:os';
import { createRequire } from 'node:module'; import { fileURLToPath } from 'node:url'; import { spawnSync } from 'node:child_process';
import { one, CONFIG_GRID } from './lib.mjs';
const HERE = path.dirname(fileURLToPath(import.meta.url)); const W = path.join(HERE, 'work'); const RES = path.join(HERE, 'results');
const require = createRequire(import.meta.url);
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const NS = arg('--n', '1,4,16').split(',').map(Number); const REPS = +arg('--reps', 5); const SFX = arg('--sfx', ''); const TARGET_MS = +arg('--target-ms', 150); const RUNS = +arg('--runs', 1);
const env = {
  rd: async (f) => fs.readFileSync(path.join(W, f)),
  createMain: () => require(path.join(W, 'dyn_main.cjs'))(),
  rss: () => process.memoryUsage().rss,
  hwm: () => +/VmHWM:\s+(\d+)/.exec(fs.readFileSync('/proc/self/status', 'utf8'))[1] * 1024,
  loadavg: () => os.loadavg().map((x) => +x.toFixed(2)),
  info: { runtime: 'node ' + process.version, cpus: os.cpus().length },
};
const emit = (o) => { fs.mkdirSync(RES, { recursive: true }); fs.appendFileSync(path.join(RES, 'p8.jsonl'), JSON.stringify(o) + '\n'); console.log(JSON.stringify(o)); };
function child(mode, cfg, N) {
  const r = spawnSync(process.execPath, [process.argv[1], '--one', mode, cfg, String(N), '--reps', String(REPS), '--sfx', SFX, '--target-ms', String(TARGET_MS)], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] });
  if (r.status !== 0) emit({ mode, cfg: cfg + SFX, N, runtime: env.info.runtime, error: (r.stdout || '').slice(-300) || `exit ${r.status}${r.signal ? ' ' + r.signal : ''}` });
  else process.stdout.write(r.stdout);
}
const oi = argv.indexOf('--one');
if (oi >= 0) { const r = await one(env, argv[oi + 1], argv[oi + 2], +argv[oi + 3], { sfx: SFX, reps: REPS, targetMs: TARGET_MS }); emit(r); process.exit(0); }
const mode = argv[0];
const runs = { steady: RUNS, startup: Math.max(RUNS, REPS), memory: 1 }[mode];
for (const N of NS) for (const cfg of CONFIG_GRID[mode]) {
  if (cfg.startsWith('static') && ![1, 4, 16].includes(N)) continue;
  for (let r = 0; r < runs; r++) child(mode, cfg, N);
}
