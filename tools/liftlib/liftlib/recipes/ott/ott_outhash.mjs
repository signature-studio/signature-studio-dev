// ott_outhash.mjs — OTT wasm の processReplacing 出力 (512 cell) を param/入力/分岐フラグの組合せで SHA-256 化する。
//   2 つの wasm (liftlib 生成 helper 版 vs 元 m10 成果物) の出力 bit 同一性の確認用 (E4/E5 より厳密)。
import crypto from 'node:crypto';
const m2 = await import(process.env.OTT_CJS);
const OBJ = 0x30310000, IN_A = 0x30320000, OU_A = 0x30330000, BUF = 0x30340000, N = 256;
const f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const res = {};
for (const val of [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]) for (const f248 of [0, 1]) for (const amp of [0.0, 0.3, 1.0]) {
  const mod = await (m2.default ? m2.default() : m2());
  if (mod._m6_data_install) mod._m6_data_install();
  const U8 = mod.HEAPU8, U32 = mod.HEAPU32, F32 = mod.HEAPF32;
  mod._function_18011d400(BigInt(OBJ), 0n);
  for (let i = 0; i < 20; i++) mod._function_180120af0(BigInt(OBJ), BigInt(i), i === 19 ? 0n : f32b(val));
  mod._function_180120800(BigInt(OBJ));
  U8[OBJ + 0x248] = f248;
  for (let i = 0; i < N; i++) {
    F32[(BUF / 4) + i] = Math.fround((Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3) * amp);
    F32[(BUF / 4) + N + i] = Math.fround(Math.cos(i * 0.13) * 0.5 * amp);
  }
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + N * 4; U32[OU_A / 4] = BUF + N * 8; U32[OU_A / 4 + 2] = BUF + N * 12;
  for (let rep = 0; rep < 2; rep++) mod._function_18011ec20(BigInt(OBJ), BigInt(IN_A), BigInt(OU_A), BigInt(N));
  const h = crypto.createHash('sha256').update(Buffer.from(U8.slice(BUF + N * 8, BUF + N * 16))).digest('hex').slice(0, 16);
  res[`p${val}_f${f248}_a${amp}`] = h;
}
console.log(JSON.stringify(res));
