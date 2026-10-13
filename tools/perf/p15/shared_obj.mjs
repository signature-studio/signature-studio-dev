// P15: 1 instance (= 1 Memory) の中に OTT 処理オブジェクトを M 個畳み込んだとき、各オブジェクトが
// 単独 instance と同じ署名を出すか (状態の分離・共有静的データの非汚染) を node で検証する。
//   node tools/perf/p15/shared_obj.mjs <ottl.cjs> <M> [BLK=1000]
// 判定: 各 obj の署名 == 単独 instance (M=1) の既知署名 (ott_x64c_bench の 6b1696f0)。
import path from 'node:path';
import { load } from '../../ott/diff/api.mjs';

const f = path.resolve(process.argv[2]); const M = Number(process.argv[3] || 1);
const BLK = Number(process.argv[4] || 1000);
const N = 128;
const OBJ0 = 0x31000000, STRIDE = 0x40000;
const IN0 = 0x34000000, OU0 = 0x34000080, BUF0 = 0x34100000;
const slot = (i) => ({ obj: OBJ0 + i * STRIDE, inA: IN0 + i * 0x100, ouA: OU0 + i * 0x100, buf: BUF0 + i * 0x2000 });

const t0 = performance.now();
const api = await load(f);
const tLoad = performance.now() - t0;
const mod = api.mod; const U32 = mod.HEAPU32, F32 = mod.HEAPF32;

const t1 = performance.now();
for (let i = 0; i < M; i++) {
  const s = slot(i);
  api.ctor(s.obj); for (let p = 0; p < 19; p++) api.setParam(s.obj, p, 0.5); api.resume(s.obj);
  for (let k = 0; k < N * 2; k++) F32[s.buf / 4 + k] = Math.fround(Math.sin(k * 0.05) * 0.5);
  U32[s.inA / 4] = s.buf; U32[s.inA / 4 + 2] = s.buf + N * 4; U32[s.ouA / 4] = s.buf + N * 8; U32[s.ouA / 4 + 2] = s.buf + N * 12;
}
const tSetup = performance.now() - t1;

const sigs = [];
for (let i = 0; i < M; i++) {
  const s = slot(i); let h = 0x811c9dc5 >>> 0;
  for (let k = 1; k <= 1000; k++) { api.process(s.obj, s.inA, s.ouA, N); if (k <= 8 || k === 1000) for (let j = 0; j < 2 * N; j++) h = Math.imul(h ^ U32[s.buf / 4 + 2 * N + j], 16777619) >>> 0; }
  sigs.push(h.toString(16));
}
const uniq = [...new Set(sigs)];

for (let i = 0; i < M; i++) { const s = slot(i); for (let k = 0; k < 300; k++) api.process(s.obj, s.inA, s.ouA, N); }
const per = [];
for (let r = 0; r < 7; r++) {
  const t = performance.now();
  for (let b = 0; b < BLK; b++) for (let i = 0; i < M; i++) { const s = slot(i); api.process(s.obj, s.inA, s.ouA, N); }
  per.push((performance.now() - t) * 1000 / (BLK * M));
}
const p50 = [...per].sort((a, b) => a - b)[3];
console.log(JSON.stringify({ runtime: `node ${process.version}`, mode: 'shared_memory_objs', M, instances: 1, blk: BLK,
  load_ms: +tLoad.toFixed(2), setup_ms: +tSetup.toFixed(2), us_per_block_p50: +p50.toFixed(2), sig_unique: uniq, sig_n: sigs.length, sig_ok: uniq.length === 1 && uniq[0] === '6b1696f0' }));
