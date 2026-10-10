// m10_bandtrace.mjs: processReplacing を 1-sample 毎に実行し, band state 0 (obj+0x140) の
// y/x 状態cell と out 先頭の変化を記録 → junk 生成過程の実測。
const VA_BASE = 0x30000000;
const M9 = new URL('../m9/work/ott_m9.cjs', import.meta.url).pathname;
const m2 = await import(M9);
const mod = await (m2.default ? m2.default() : m2());
if (mod._m6_data_install) mod._m6_data_install();
const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const dv = new DataView(U8.buffer, U8.byteOffset, U8.length);
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
mod._function_18011d400(BigInt(OBJ), 0n);
for (let i = 0; i < 20; i++) mod._function_180120af0(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(0.5));
mod._function_180120800(BigInt(OBJ));
U8[OBJ + 0x248] = 0;
// 入力 = k 毎の単調小信号 (sin) ；OUT は独立 buf
const N = 1;
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4;
U32[OU_A / 4] = BUF + 0x10000; U32[OU_A / 4 + 2] = BUF + 0x10000 + N * 4;
const st0 = dv.getUint32(OBJ + 0x140, true);
const st1 = dv.getUint32(OBJ + 0x148, true);
const st2 = dv.getUint32(OBJ + 0x150, true);
const st3 = dv.getUint32(OBJ + 0x158, true);
const log = [];
for (let k = 0; k < 64; k++) {
  F32[BUF / 4] = Math.fround(Math.sin(k * 0.05) * 0.7 + Math.cos(k * 0.011) * 0.3);
  mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
  const row = {
    k,
    in: dv.getFloat32(BUF, true),
    y0: dv.getFloat64(st0 + 8, true), xin: dv.getFloat64(st0 + 0x48, true),
    yR: dv.getFloat64(st1 + 8, true),
    yHP: dv.getFloat64(st2 + 0x28, true),
    yHPR: dv.getFloat64(st3 + 0x28, true),
  };
  if (F32[BUF + 0x10000] !== 0) row.out = dv.getFloat32(BUF + 0x10000, true);
  log.push(row);
}
console.log(JSON.stringify(log));
