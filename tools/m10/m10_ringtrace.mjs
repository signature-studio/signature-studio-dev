// m10_ringtrace.mjs: [0x248]=0 path chunk (=4sample) 実行毎に ring [0x250](6)/[0x258](8) 先頭 cell 値を記録。
// junk 開始 リング/サンプルを特定する。
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
const N = 256, CH = 4;
for (let i = 0; i < N; i++) {
  F32[(BUF / 4) + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3);
  F32[(BUF / 4) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5);
}
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4;
U32[OU_A / 4] = BUF + 0x20000; U32[OU_A / 4 + 2] = BUF + 0x20000 + N * 4;
const ringIN = dv.getUint32(OBJ + 0x250, true);
const ringOut = dv.getUint32(OBJ + 0x258, true);
const rIn = [], rOut = [];
for (let j = 0; j < 6; j++) rIn.push(dv.getUint32(ringIN + j * 8, true));
for (let j = 0; j < 8; j++) rOut.push(dv.getUint32(ringOut + j * 8, true));
const rows = [];
for (let done = 0; done < N; done += CH) {
  U32[IN_A / 4] = BUF + done * 4; U32[IN_A / 4 + 2] = BUF + N * 4 + done * 4;
  U32[OU_A / 4] = BUF + 0x20000; U32[OU_A / 4 + 2] = BUF + 0x20000 + N * 4;
  try {
    mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(CH));
  } catch (e) { rows.push({ k: done, e: String(e && e.message || e).slice(0, 60) }); break; }
  const rec = { k: done };
  for (let j = 0; j < 6; j++) rec['i' + j] = dv.getFloat64(rIn[j] + done * 8, true);
  for (let j = 0; j < 8; j++) rec['o' + j] = dv.getFloat64(rOut[j] + done * 8, true);
  rows.push(rec);
}
console.log(JSON.stringify(rows));
