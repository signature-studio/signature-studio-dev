// trace_wasm.mjs: 標準シナリオを ott_trace.cjs (entry hook 付) で実行し, 関数 entry ログ + alloc log + 入力を JSON に出す。
//   env: MOD OUT [PVAL] [F248] [N] [P4]
import fs from 'fs';
import zlib from 'zlib';
import { load } from './api.mjs';
const api = await load(process.env.MOD);
const mod = api.mod;
const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const N = Number(process.env.N || 256), PVAL = Number(process.env.PVAL || 0.5);
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const inp = new Float32Array(N * 2);
for (let i = 0; i < N; i++) { inp[i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3); inp[N + i] = Math.fround(Math.cos(i * 0.13) * 0.5); }
for (let i = 0; i < N * 2; i++) F32[BUF / 4 + i] = inp[i];
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4;
U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
U32[0x34000004 / 4] = 1;
const marks = {};
const mk = (nm) => { marks[nm] = U32[0x34000000 / 4]; };
api.ctor(OBJ); mk('ctor');
for (let i = 0; i < 19; i++) api.setParam(OBJ, i, i === 4 && process.env.P4 !== undefined ? Number(process.env.P4) : PVAL);
mk('setp');
api.resume(OBJ); mk('resume');
if (process.env.F248 !== undefined && process.env.F248 !== '') U8[OBJ + 0x248] = Number(process.env.F248);
api.process(OBJ, IN_A, OU_A, N); mk('proc');
const n = U32[0x34000000 / 4];
const tr = [];
for (let i = 0; i < n; i++) { const b = 0x34000010 / 4 + i * 10; const r = []; for (let k = 0; k < 5; k++) r.push(((BigInt(U32[b + 2 * k + 1]) << 32n) | BigInt(U32[b + 2 * k])).toString(16)); tr.push(r); }
const na = U32[0x35f00000 / 4]; const alog = [];
for (let i = 0; i < na; i++) alog.push([U32[0x35f00000 / 4 + 2 + 2 * i], U32[0x35f00000 / 4 + 3 + 2 * i]]);
const outv = []; for (let i = 0; i < N * 2; i++) outv.push(U32[(BUF + N * 8) / 4 + i]);
fs.writeFileSync(process.env.OUT, JSON.stringify({ N, PVAL, alog, inp: zlib.deflateSync(Buffer.from(inp.buffer)).toString('base64'), trace: tr, marks, out: outv }));
console.log('[trace_wasm] records', n, JSON.stringify(marks));
