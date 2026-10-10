// m10_junksrc.mjs: e2e 手順と同一の full N=256 呼出後, out L/R と全部 ring/state の bits 突合データを出す。
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

const u64 = (p) => dv.getBigUint64(p, true).toString(16);
const out = { outL: [], outR: [], ringO: [], ringI: [], states: [] };
for (let i = 0; i < N; i++) out.outL.push(u64(BUF + N * 8 + i * 4));
for (let i = 0; i < N; i++) out.outR.push(u64(BUF + N * 12 + i * 4));
const ringIN = dv.getUint32(OBJ + 0x250, true);
const ringOut = dv.getUint32(OBJ + 0x258, true);
for (let j = 0; j < 6; j++) {
  const p = dv.getUint32(ringIN + j * 8, true);
  const arr = [];
  for (let i = 0; i < N; i++) arr.push(u64(p + i * 8));
  out.ringI.push(arr);
}
for (let j = 0; j < 8; j++) {
  const p = dv.getUint32(ringOut + j * 8, true);
  const arr = [];
  for (let i = 0; i < N; i++) arr.push(u64(p + i * 8));
  out.ringO.push(arr);
}
// states: 8 band pointers obj+0x140..0x17c + 16 svf obj+0x180..0x1f8
for (let k = 0; k < 8; k++) {
  const p = dv.getUint32(OBJ + 0x140 + k * 8, true);
  const arr = [];
  for (let o = 0; o < 0xe0; o += 8) arr.push(u64(p + o));
  out.states.push({ kind: 'band', idx: k, p, cells: arr });
}
for (let k = 0; k < 16; k++) {
  const p = dv.getUint32(OBJ + 0x180 + k * 8, true);
  const arr = [];
  for (let o = 0; o < 0x30; o += 4) arr.push(u64(p + o));
  out.states.push({ kind: 'svf', idx: k, p, cells: arr });
}
console.log(JSON.stringify(out));
