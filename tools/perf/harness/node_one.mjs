// 1 変種 × 1 プロセスの node ベンチ。結果を 1 行 JSON で stdout へ。
//   node [v8flags] node_one.mjs <ott|a1|a2> <variantDir> [iters] [head]
import fs from 'node:fs';
import * as B from './bench_core.mjs';
const [,, kind = 'ott', variant = 'o2', iters = '20000', head = '300'] = process.argv;
const W = new URL('../work/', import.meta.url).pathname;
const out = { env: 'node', v8: process.versions.v8, node: process.version, kind, variant, execArgv: process.execArgv.join(' ') };
const base = kind === 'ott' ? `${W}ott/${variant}` : `${W}${kind}/${variant}`;
const glue = kind === 'ott' ? `${base}/ott.mjs` : `${base}/${kind}.mjs`;
const wasmFile = glue.replace(/\.mjs$/, '.wasm');
out.wasmBytes = fs.statSync(wasmFile).size;
const mk = (await import(glue)).default;
const t0 = performance.now();
const mod = await mk();
out.createMs = performance.now() - t0;
out.rssAfterCreateMB = process.memoryUsage().rss / 1048576;
let call;
if (kind === 'ott') {
  Object.assign(out, B.ottInit(mod));
  out.signature = B.ottSignature(mod);
  call = () => B.ottBlock(mod);
} else {
  out.signature = B.m5Signature(mod, kind);
  B.m5Init(mod, kind); call = () => B.m5Block(mod, kind);
}
const t1 = performance.now(); call(); out.firstCallMs = performance.now() - t1;
const batch = kind === 'ott' ? 1 : 64;
const r = B.runBlocks(call, { warmup: 300, iters: +iters, head: +head, batch });
out.head = r.head.map((x) => +x.toFixed(4));
out.steady = r.steady;
out.rtf44 = r.steady.p50 / B.BUDGET.k44; out.rtf48 = r.steady.p50 / B.BUDGET.k48;
out.rtf44p99 = r.steady.p99 / B.BUDGET.k44;
if (kind === 'ott') out.checksum = B.ottChecksum(mod);
out.rssEndMB = process.memoryUsage().rss / 1048576;
console.log(JSON.stringify(out));
