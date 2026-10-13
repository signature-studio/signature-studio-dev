// 署名 probe: node synth_probe.mjs <module.cjs> → {"sig":"<fnv32 hex>"} (tools/perf/harness/ott_x64c_bench.mjs と同形式)
import path from 'node:path';
import { createRequire } from 'node:module';
const M = await createRequire(import.meta.url)(path.resolve(process.argv[2]))();
const N = 257, pi = M._malloc(N * 4), po = M._malloc(N * 4 + 4);
let h = 0x811c9dc5 >>> 0, s = 12345;
const rnd = () => { s = (Math.imul(s, 1103515245) + 12345) >>> 0; return s; };
for (let rep = 0; rep < 50; rep++) {
  const n = 1 + (rnd() % N);
  for (let i = 0; i < n; i++) { const u = rnd(); M.HEAPU32[(pi >> 2) + i] = ((u & 0x80000000) | (((u >>> 23) & 0x3f) + 100) << 23 | (u & 0x7fffff)) >>> 0; }
  const r = M._synth_run(pi, po, n);
  h = Math.imul(h ^ new Uint32Array(new Float32Array([r]).buffer)[0], 16777619) >>> 0;
  for (let i = 0; i < n; i++) h = Math.imul(h ^ M.HEAPU32[(po >> 2) + i], 16777619) >>> 0;
}
console.log(JSON.stringify({ sig: h.toString(16) }));
