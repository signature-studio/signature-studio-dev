// node 側ベンチ オーケストレータ。各 (kind,variant,mode,rep) を別プロセスで実行し results/node_<tag>.json に集約。
//   node node_bench.mjs <tag> <kind> <variants,comma> [--modes default,liftoff,tf] [--reps 3] [--iters 20000]
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
const a = process.argv.slice(2);
const [tag, kind, vlist] = a;
const opt = (k, d) => { const i = a.indexOf('--' + k); return i >= 0 ? a[i + 1] : d; };
const modes = opt('modes', 'default').split(',');
const reps = +opt('reps', 3), iters = opt('iters', '20000');
const MODEFLAGS = { default: [], liftoff: ['--liftoff-only'], tf: ['--no-liftoff'], eager: ['--no-wasm-lazy-compilation'] };
const here = new URL('./', import.meta.url).pathname;
const jf = new URL(`../results/node_${tag}.jsonl`, import.meta.url).pathname;
fs.mkdirSync(new URL('../results/', import.meta.url).pathname, { recursive: true });
const done = new Set(fs.existsSync(jf) ? fs.readFileSync(jf, 'utf8').split('\n').filter(Boolean).map((l) => { const j = JSON.parse(l); return j.error ? "" : `${j.kind}/${j.variant}/${j.mode}/${j.rep}`; }) : []);
const out = [];
for (const v of vlist.split(',')) for (const m of modes) for (let r = 0; r < reps; r++) {
  if (done.has(`${kind}/${v}/${m}/${r}`)) continue;   // 再開可能 (サーバ再起動対策)
  const la = os.loadavg()[0];
  try {
    const s = execFileSync(process.execPath, [...MODEFLAGS[m], here + 'node_one.mjs', kind, v, iters, '300'], { encoding: 'utf8', maxBuffer: 1 << 26 });
    const j = JSON.parse(s.trim().split('\n').pop()); j.mode = m; j.rep = r; j.load = la; out.push(j); fs.appendFileSync(jf, JSON.stringify(j) + '\n');
    console.error(`${kind}/${v}/${m}/${r} p50=${j.steady.p50.toFixed(4)}ms p99=${j.steady.p99.toFixed(4)} rtf44=${j.rtf44.toFixed(5)} sig=${j.signature} load=${la.toFixed(1)}`);
  } catch (e) { console.error(`${kind}/${v}/${m}/${r} FAIL ${String(e.message).slice(0, 200)}`); const ej = { kind, variant: v, mode: m, rep: r, error: String(e.message).slice(0, 300) }; out.push(ej); fs.appendFileSync(jf, JSON.stringify(ej) + '\n'); }
}
console.error('done', jf);
