// perf.mjs: lifted wasm の processReplacing 速度 (実時間比)。env: MOD [BLOCKS] [N]
import { load } from './api.mjs';
const api = await load(process.env.MOD); const mod = api.mod; const U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000, N = Number(process.env.N || 256), B = Number(process.env.BLOCKS || 2000);
api.ctor(OBJ); for (let i = 0; i < 19; i++) api.setParam(OBJ, i, 0.5); api.resume(OBJ);
for (let i = 0; i < N * 2; i++) F32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.5);
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
for (let k = 0; k < 50; k++) api.process(OBJ, IN_A, OU_A, N);
const t0 = process.hrtime.bigint();
for (let k = 0; k < B; k++) api.process(OBJ, IN_A, OU_A, N);
const dt = Number(process.hrtime.bigint() - t0) / 1e9;
const audio = B * N / 44100;
console.log(JSON.stringify({ blocks: B, n: N, seconds: dt.toFixed(3), audio_seconds: audio.toFixed(2), realtime_x: (audio / dt).toFixed(1), us_per_block: (dt / B * 1e6).toFixed(1) }));
