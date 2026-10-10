// m10_coefdump.mjs: build 後の band 状態係数を JSON で吐く (m10_coefref.py との突合用)。
const VA_BASE = 0x30000000;
const M10 = process.env.M10_DIR + '/work/ott_m10.cjs';
const m2 = await import(M10);
const mod = await (m2.default ? m2.default() : m2());
if (mod._m6_data_install) mod._m6_data_install();
const dv = new DataView(mod.HEAPU8.buffer, mod.HEAPU8.byteOffset, mod.HEAPU8.length);
const OBJ = 0x30310000;
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
mod._function_18011d400(BigInt(OBJ), 0n);
for (let i = 0; i < 20; i++) mod._function_180120af0(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(0.5));
mod._function_180120800(BigInt(OBJ));
const offs = { A16: 0x98, A32: 0xa0, B16: 0xa8, B32: 0xb0, D1: 0x68, C1c: 0x70, C16: 0x78, D2: 0x88, E2: 0x90, F2: 0x80 };
const out = [];
for (let k = 0; k < 8; k++) {
  const st = dv.getUint32(OBJ + 0x140 + 8 * k, true);
  const cells = {};
  for (const [nm, off] of Object.entries(offs)) cells[off] = dv.getFloat64(st + off, true);
  out.push({ k, st, cells });
}
console.log(JSON.stringify(out));
