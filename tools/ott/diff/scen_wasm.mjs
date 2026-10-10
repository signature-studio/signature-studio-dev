// scen_wasm.mjs: 標準シナリオ (ctor → setParameter 0..18 → resume → processReplacing N) を wasm 側で実行し,
// 各 stage で heap/obj/IO を zlib+b64 で dump (native 参照と byte 比較するため)。
//   env: MOD=ott.cjs OUT=stages_wasm.json [PVAL=0.5] [F248=] [N=256] [P4=]
import fs from 'fs';
import zlib from 'zlib';
import { load } from './api.mjs';
const api = await load(process.env.MOD);
const mod = api.mod;
const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const N = Number(process.env.N || 256);
const PVAL = Number(process.env.PVAL || 0.5);
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const z = (a) => zlib.deflateSync(Buffer.from(a)).toString('base64');
const regions = () => {
  const n = U32[0x35f00000 / 4];
  const r = [['obj', OBJ, 0x1000]];
  for (let i = 0; i < n; i++) r.push(['h' + i, U32[0x35f00000 / 4 + 2 + 2 * i], U32[0x35f00000 / 4 + 3 + 2 * i]]);
  r.push(['io', BUF, N * 16]);
  return r;
};
const stages = {};
const snap = (nm) => { stages[nm] = regions().map(([k, p, s]) => ({ k, p, s, z: z(U8.slice(p, p + s)) })); };
// inputs
const inp = new Float32Array(N * 2);
for (let i = 0; i < N; i++) { inp[i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3); inp[N + i] = Math.fround(Math.cos(i * 0.13) * 0.5); }
for (let i = 0; i < N * 2; i++) F32[BUF / 4 + i] = inp[i];
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4;
U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
api.ctor(OBJ); snap('ctor');
for (let i = 0; i < 19; i++) api.setParam(OBJ, i, i === 4 && process.env.P4 !== undefined ? Number(process.env.P4) : PVAL);
snap('setp');
api.resume(OBJ); snap('resume');
if (process.env.F248 !== undefined && process.env.F248 !== '') U8[OBJ + 0x248] = Number(process.env.F248);
api.process(OBJ, IN_A, OU_A, N); snap('proc');
const alog = [];
const n = U32[0x35f00000 / 4];
for (let i = 0; i < n; i++) alog.push([U32[0x35f00000 / 4 + 2 + 2 * i], U32[0x35f00000 / 4 + 3 + 2 * i]]);
fs.writeFileSync(process.env.OUT, JSON.stringify({ N, PVAL, alog, inp: z(new Uint8Array(inp.buffer)), stages }));
console.log('[scen_wasm] stages', Object.keys(stages).join(','), 'allocs', n);
