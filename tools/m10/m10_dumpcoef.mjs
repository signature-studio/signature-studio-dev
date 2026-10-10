// m10_dumpcoef.mjs (M10): 既存 wasm (tools/m9/work/ott_m9.cjs) の band state 係数を全ダンプ。
// 各 band state = [obj+0x140+8k] (4 個): f64 係数 [st+0x60..0xe0] + 状態 [st+8..0x60] を JSON 出力。
const VA_BASE = 0x30000000;
const M9 = new URL('../m9/work/ott_m9.cjs', import.meta.url).pathname;
const m2 = await import(M9);
const mod = await (m2.default ? m2.default() : m2());
if (mod._m6_data_install) mod._m6_data_install();
const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
const dv = new DataView(U8.buffer, U8.byteOffset, U8.length);
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000;
const N = 256;
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const d64b = (p) => dv.getBigUint64(p, true);

mod._function_18011d400(BigInt(OBJ), 0n);
for (let i = 0; i < 20; i++) mod._function_180120af0(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(0.5));
mod._function_180120800(BigInt(OBJ));
U8[OBJ + 0x248] = 0;
for (let i = 0; i < N; i++) {
  F32[(BUF / 4) + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3);
  F32[(BUF / 4) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5);
}
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4;
U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));

// band states: obj+0x140..0x158 (4)
const off = {
  coef: [[0x68, 'D1'], [0x70, 'C1c'], [0x78, 'C16'], [0x80, 'F2'], [0x88, 'D2'], [0x90, 'E2'],
         [0x98, 'A16'], [0xa0, 'A32'], [0xa8, 'B16'], [0xb0, 'B32'], [0xc0, 'C1c2'], [0xc8, 'D1_2'],
         [0xd0, 'D2_2'], [0xd8, 'F2_2']],
  state: [[8, 'y0'], [0x10, 'y1'], [0x18, 'y2'], [0x20, 'y3'], [0x28, 'v4'], [0x30, 'v5'],
          [0x38, 'v6'], [0x40, 'v7'], [0x48, 'x0'], [0x50, 'x1'], [0x58, 'x2'], [0x60, 'x3']]
};
const out = [];
for (let k = 0; k < 4; k++) {
  const st = dv.getUint32(OBJ + 0x140 + 8 * k, true);
  const rec = { idx: k, stVA: st };
  for (const [o, nm] of off.coef) rec[nm] = dv.getFloat64(st + o, true).toString();
  for (const [o, nm] of off.state) rec[nm] = dv.getFloat64(st + o, true).toString();
  out.push(rec);
}
console.log(JSON.stringify(out, null, 1));
