// m10_junksrc2.mjs: IR からの liner memory 情報付きダンプ。実行とともにスキャン済み junk 入口を探す。
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

const dump = (name, p, n) => { const a = []; for (let i = 0; i < n; i++) a.push(dv.getBigUint64(p + i * 8, true).toString(16)); return a; };
const res = {};
for (const off of [0x200, 0x208, 0x210, 0x240, 0x290, 0x2a0, 0x288, 0x298]) res['o' + off] = dv.getUint32(OBJ + off, true);
// [rbp+0x238/0x23c] = obj+0x238 f32
res.gainL = dv.getFloat32(OBJ + 0x238, true);
res.gainR = dv.getFloat32(OBJ + 0x23c, true);
res.mix2f8 = dv.getFloat32(OBJ + 0x2f8, true);
res['c2a8'] = dv.getUint32(OBJ + 0x2a8, true);
res['c2ac'] = dv.getUint32(OBJ + 0x2ac, true);
res['c2b0'] = dv.getUint32(OBJ + 0x2b0, true);
res.ring0_250 = dump('r250slice0', dv.getUint32(dv.getUint32(OBJ + 0x250, true), true), 128);
res.ring1_250 = dump('r250slice1', dv.getUint32(dv.getUint32(OBJ + 0x250, true) + 8, true), 128);
res.ringOa = dump('ro0', dv.getUint32(dv.getUint32(OBJ + 0x258, true), true), 128);
res.ringOb = dump('ro1', dv.getUint32(dv.getUint32(OBJ + 0x258, true) + 8, true), 128);
res.ringOc = dump('ro2', dv.getUint32(dv.getUint32(OBJ + 0x258, true) + 0x10, true), 128);
res.ringOd = dump('ro3', dv.getUint32(dv.getUint32(OBJ + 0x258, true) + 0x18, true), 128);
res.ringOe = dump('roe', dv.getUint32(dv.getUint32(OBJ + 0x258, true) + 0x20, true), 128);
res.ringOf = dump('rof', dv.getUint32(dv.getUint32(OBJ + 0x258, true) + 0x28, true), 128);
res.ringOg = dump('rog', dv.getUint32(dv.getUint32(OBJ + 0x258, true) + 0x30, true), 128);
res.ringOh = dump('roh', dv.getUint32(dv.getUint32(OBJ + 0x258, true) + 0x38, true), 128);
// lbs (the level computer states [rbp+0x200..]) = linearmem dumps:
for (const k of [0x200, 0x208, 0x210]) {
  const p = dv.getUint32(OBJ + k, true);
  const arr = [];
  for (let o = 0x50; o < 0xc0; o += 8) arr.push(dv.getBigUint64(p + o, true).toString(16));
  res['lb' + k.toString(16)] = arr;
}
console.log(JSON.stringify(res));
