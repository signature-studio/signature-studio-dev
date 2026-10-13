// reloc_multi.mjs <ottl.cjs> <N> : N 個の独立 wasm インスタンスを、それぞれ別の gbase (0x30000000 + k*0x200000) に敷設して署名を比較
import path from 'node:path';
const f = process.argv[2], NI = Number(process.argv[3] ?? 16);
const m2 = await import(path.resolve(f));
const create = m2.default ? m2.default : m2;
const f32b = (v) => { const fa = new Float32Array(1); fa[0] = v; return BigInt(new Uint32Array(fa.buffer)[0]); };
const big = (x) => BigInt(x);
const NB = 128;
const sigs = [];
for (let k = 0; k < NI; k++) {
  const GB = 0x30000000 + k * 0x200000;
  const mod = await create();
  mod._ott_set_gbase(BigInt(GB));
  mod._ott_data_install();
  const toVa = (va) => GB + (va - 0x180000000);
  const run = (va, a, x = []) => BigInt.asUintN(64, mod._ott_run(toVa(va), big(a[0] ?? 0), big(a[1] ?? 0), big(a[2] ?? 0), big(a[3] ?? 0), big(x[0] ?? 0), big(x[1] ?? 0), big(x[2] ?? 0), big(x[3] ?? 0)));
  const U32 = mod.HEAPU32, F32 = mod.HEAPF32;
  const OBJ = GB + 0x10000, IN_A = GB + 0x20000, OU_A = GB + 0x30000, BUF = GB + 0x40000;
  run(0x18011d400, [OBJ, 0]);
  for (let i = 0; i < 19; i++) run(0x180120af0, [OBJ, i], [0, 0, f32b(0.5)]);
  run(0x180120800, [OBJ]);
  for (let i = 0; i < NB * 2; i++) F32[BUF / 4 + i] = Math.fround(Math.sin(i * 0.05) * 0.5);
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + NB * 4; U32[OU_A / 4] = BUF + NB * 8; U32[OU_A / 4 + 2] = BUF + NB * 12;
  let h = 0x811c9dc5 >>> 0;
  for (let j = 1; j <= 1000; j++) {
    run(0x18011ec20, [OBJ, IN_A, OU_A, NB]);
    if (j <= 8 || j === 1000) for (let i = 0; i < 2 * NB; i++) h = Math.imul(h ^ U32[BUF / 4 + 2 * NB + i], 16777619) >>> 0;
  }
  let nz = 0; for (let i = 0; i < 2 * NB; i++) if (F32[BUF / 4 + 2 * NB + i] !== 0) nz++;
  const sig = h.toString(16);
  sigs.push(sig);
  console.log(JSON.stringify({ inst: k, gbase: '0x' + GB.toString(16), sig, nonzeroOut: nz }));
}
const ok = sigs.every((s) => s === '6b1696f0');
console.log(JSON.stringify({ N: NI, all_6b1696f0: ok }));
process.exit(ok ? 0 : 1);
