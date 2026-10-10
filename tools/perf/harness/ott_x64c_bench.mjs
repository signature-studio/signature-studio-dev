// bit-exact OTT (tools/ott x64c lift) の processReplacing 128f ベンチ。 node ott_x64c_bench.mjs <work/ott_x64c/v.cjs> [reps]
// 出力: 署名 (全変種で一致すべき) / p50 / p99 / RTF@44.1k
import path from 'node:path';
import { load } from '../../ott/diff/api.mjs';
const f = process.argv[2], N = 128, B = 20000;
const api = await load(path.resolve(f)); const mod = api.mod; const U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
api.ctor(OBJ); for (let i = 0; i < 19; i++) api.setParam(OBJ, i, 0.5); api.resume(OBJ);
for (let i = 0; i < N * 2; i++) F32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.5);
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
let h = 0x811c9dc5 >>> 0;
for (let k = 1; k <= 1000; k++) { api.process(OBJ, IN_A, OU_A, N); if (k <= 8 || k === 1000) for (let i = 0; i < 2 * N; i++) h = Math.imul(h ^ U32[BUF / 4 + 2 * N + i], 16777619) >>> 0; }
let nz = 0; for (let i = 0; i < 2 * N; i++) if (F32[BUF / 4 + 2 * N + i] !== 0) nz++;
const per = new Float64Array(B);
for (let k = 0; k < 300; k++) api.process(OBJ, IN_A, OU_A, N);
for (let k = 0; k < B; k++) { const t = performance.now(); api.process(OBJ, IN_A, OU_A, N); per[k] = performance.now() - t; }
per.sort();
console.log(JSON.stringify({ f: path.basename(f), sig: h.toString(16), nonzeroOut: nz, p50us: +(per[B >> 1] * 1000).toFixed(2), p99us: +(per[Math.floor(B * .99)] * 1000).toFixed(2), rtf44: +(per[B >> 1] / (128 / 44.1)).toFixed(5) }));
