// old_census.mjs: M10 e2e_check.mjs と同じ harness (params 0..19, param19=0, [0x248] 強制) で旧 RetDec chain の census を再現する (before 値)
import { load } from './api.mjs';
const api = await load(process.env.MOD);
const mod = api.mod, U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const dv = new DataView(U8.buffer, U8.byteOffset, U8.length);
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000, N = 256;
function setup(val) {
  api.ctor(OBJ);
  for (let i = 0; i < 20; i++) api.setParam(OBJ, i, i === 19 ? 0 : val);
  api.resume(OBJ); U8[OBJ + 0x248] = 0;
  for (let i = 0; i < N; i++) { F32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3); F32[BUF / 4 + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5); }
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
}
const cens = (f248) => {
  setup(0.5); U8[OBJ + 0x248] = f248; api.process(OBJ, IN_A, OU_A, N);
  const r = { zero: 0, normal: 0, junkHi: 0, junkTiny: 0, nan: 0, absmax: 0 };
  for (let ch = 0; ch < 2; ch++) for (let i = 0; i < N; i++) {
    const v = dv.getFloat32(BUF + N * 8 + ch * N * 4 + i * 4, true), a = Math.abs(v);
    if (a > r.absmax) r.absmax = a;
    if (v === 0) r.zero++; else if (Number.isNaN(v)) r.nan++; else if (a >= 4) r.junkHi++; else if (a <= 1e-18) r.junkTiny++; else r.normal++;
  }
  return r;
};
console.log(JSON.stringify({ f248_0: cens(0), f248_1: cens(1) }));
