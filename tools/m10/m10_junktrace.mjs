// m10_junktrace.mjs: [0x248]=0 path (= 0x18011f936 SVF per-sample path) を 4-sample チャンク毎に実行し,
// out L/R per-cell 値 + SVF 16 state の主要 cell を記録して junk 出生 cell を特定する。
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
const IN = 256, OUT = 256;
for (let i = 0; i < IN; i++) {
  F32[(BUF / 4) + i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3);
  F32[(BUF / 4) + IN + i] = Math.fround(Math.cos(i * 0.13) * 0.5);
}
U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + IN * 4;
U32[OU_A / 4] = BUF + 0x20000; U32[OU_A / 4 + 2] = BUF + 0x20000 + OUT * 4;
// ring pointer arrays
const ringIN = dv.getUint32(OBJ + 0x250, true);
const ringOut = dv.getUint32(OBJ + 0x258, true);
const rIn = [], rOut = [];
for (let j = 0; j < 6; j++) rIn.push(dv.getUint32(ringIN + j * 8, true));
for (let j = 0; j < 8; j++) rOut.push(dv.getUint32(ringOut + j * 8, true));
const svfPts = [];
for (let k = 0; k < 16; k++) svfPts.push(dv.getUint32(OBJ + 0x180 + 8 * k, true));

const snap = (rows, tag, k) => {
  rows.push({ k, tbl: 'outL[0]' + tag, v: dv.getFloat32(BUF + 0x20000 + (k % OUT) * 4, true) });
  rows.push({ k, tbl: 'outR' + tag, v: dv.getFloat32(BUF + 0x20000 + OUT * 4 + (k % OUT) * 4, true) });
};
const rows = [];
const CH = 4;
let done = 0;
while (done < IN) {
  const chunk = Math.min(CH, IN - done);
  // input chunk offset: IN_A[0] points at BUF; shift by advancing pointers
  U32[IN_A / 4] = BUF + done * 4; U32[IN_A / 4 + 2] = BUF + (IN * 4) + done * 4;
  U32[OU_A / 4] = BUF + 0x20000; U32[OU_A / 4 + 2] = BUF + 0x20000 + OUT * 4;
  try {
    mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(chunk));
  } catch (e) {
    rows.push({ k: done, tbl: 'THROW', v: String(e && e.message || e).slice(0, 60) });
    break;
  }
  for (let i = 0; i < chunk; i++) {
    const abs = done + i;
    rows.push({ k: abs, tbl: 'outL', v: dv.getFloat32(BUF + 0x20000 + i * 4, true) });
    rows.push({ k: abs, tbl: 'outR', v: dv.getFloat32(BUF + 0x20000 + OUT * 4 + i * 4, true) });
  }
  if (done === 32 || done === 128) {  // state snapshot at 2 points
    const s = { k: done, tbl: 'STATE', svf: [] };
    for (let kk = 0; kk < 16; kk++) {
      const p = svfPts[kk];
      s.svf.push([p + 0, p + 8, p + 0xc, p + 0x20, p + 0x24].map(o => dv.getFloat32(p + o, true)));
    }
    s.svf = s.svf.map(a => a.map(x => +x.toPrecision(6)));
    rows.push(s);
  }
  done += chunk;
}
console.log(JSON.stringify(rows));
