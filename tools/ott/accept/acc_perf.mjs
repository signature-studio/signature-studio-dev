// acc_perf.mjs — CAB-137/138 性能の独立再計測 (n≥3 レンジ, 規則 38)。
//   使い方: MOD=<.cjs> [N=256] [BLOCKS=2000] [REPEAT=5] node acc_perf.mjs
//   出力: 各 run の us_per_block / realtime_x と min–max レンジ。
//   perf.mjs と同一条件 (ctor → param×19 → resume → warmup 50 → 計測 B block)。
import { load } from '../diff/api.mjs';

const api = await load(process.env.MOD);
const mod = api.mod;
const U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const N = Number(process.env.N || 256), B = Number(process.env.BLOCKS || 2000);
const REPEAT = Number(process.env.REPEAT || 5);
api.ctor(OBJ);
for (let i = 0; i < 19; i++) api.setParam(OBJ, i, 0.5);
api.resume(OBJ);
for (let i = 0; i < N * 2; i++) F32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.5);
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
for (let k = 0; k < 50; k++) api.process(OBJ, IN_A, OU_A, N);
const runs = [];
for (let r = 0; r < REPEAT; r++) {
  const t0 = process.hrtime.bigint();
  for (let k = 0; k < B; k++) api.process(OBJ, IN_A, OU_A, N);
  const dt = Number(process.hrtime.bigint() - t0) / 1e9;
  runs.push({ us: +(dt / B * 1e6).toFixed(1), x: +((B * N / 44100) / dt).toFixed(1) });
}
const us = runs.map(r => r.us), xs = runs.map(r => r.x);
console.log(JSON.stringify({
  mod: process.env.MOD.split('/').pop(), n: N, blocks: B, repeat: REPEAT,
  us_per_block: runs.map(r => r.us), realtime_x: runs.map(r => r.x),
  us_min: Math.min(...us), us_max: Math.max(...us), x_min: Math.min(...xs), x_max: Math.max(...xs),
}));
