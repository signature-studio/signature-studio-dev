// coresident_test.mjs — 1 wasm / 1 linear memory に同一 DLL を base A=0x10000 / base B=0x400000 で同居させ (build_x64c_coresident.sh),
//   A と B を交互に駆動して標準 scenario 出力が native 一致済み単体出力と bit 一致することを確認する (CPU 状態 R/X は共有、実行は逐次)。
//   usage: node coresident_test.mjs --mod co.cjs --layout layout.sh --ref std_ref.json
import fs from 'node:fs';
const arg = (k) => { const i = process.argv.indexOf('--' + k); return process.argv[i + 1]; };
const L = Object.fromEntries(fs.readFileSync(arg('layout'), 'utf8').trim().split('\n').map((l) => l.split('=')).map(([k, v]) => [k, Number(v)]));
const ref = JSON.parse(fs.readFileSync(arg('ref'), 'utf8')).outs[0];
const mod = await (await import(arg('mod'))).default();
mod._a_data_install(); mod._b_data_install();
const n = 256, f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const mkRun = (fn, base) => (va, a, x = []) => BigInt.asUintN(64, fn(base + (va - 0x180000000), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), BigInt(a[2] ?? 0), BigInt(a[3] ?? 0), BigInt(x[0] ?? 0), BigInt(x[1] ?? 0), BigInt(x[2] ?? 0), BigInt(x[3] ?? 0)));
const I = [{ run: mkRun(mod._run_a, L.LB_BASE_A), arena: L.LB_ARENA_A }, { run: mkRun(mod._run_b, L.LB_BASE_B), arena: L.LB_ARENA_B }];
for (const t of I) { t.OBJ = t.arena + 0x10000; t.IN = t.arena + 0x20000; t.OU = t.arena + 0x30000; t.BUF = t.arena + 0x40000; }
const inp = new Float32Array(n * 2); for (let i = 0; i < n; i++) { inp[i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3); inp[n + i] = Math.fround(Math.cos(i * 0.13) * 0.5); }
for (const t of I) { // 交互に ctor / param / resume (CPU 状態共有でも逐次なら干渉しない)
  t.run(0x18011d400, [t.OBJ, 0]);
}
for (let i = 0; i < 19; i++) for (const t of I) t.run(0x180120af0, [t.OBJ, i], [0, 0, f32b(0.5)]);
for (const t of I) t.run(0x180120800, [t.OBJ]);
for (const t of I) {
  const U32 = mod.HEAPU32, F32 = mod.HEAPF32; U32[t.IN / 4] = t.BUF; U32[t.IN / 4 + 2] = t.BUF + n * 4; U32[t.OU / 4] = t.BUF + n * 8; U32[t.OU / 4 + 2] = t.BUF + n * 12; F32.set(inp, t.BUF / 4);
  t.run(0x18011ec20, [t.OBJ, t.IN, t.OU, n]);
  t.out = Array.from(mod.HEAPU32.subarray((t.BUF + n * 8) / 4, (t.BUF + n * 8) / 4 + 2 * n));
}
const eq = I.map((t) => t.out.every((v, i) => v === ref[i]));
console.log(`INFO co-resident: 1 wasm, linear memory ${(mod.HEAPU8.length / 1048576)} MiB に OTT×2 (base 0x${L.LB_BASE_A.toString(16)} / 0x${L.LB_BASE_B.toString(16)})`);
console.log(`${eq.every(Boolean) ? 'OK  ' : 'FAIL'} X2 同居 2 DLL の交互駆動出力が native 一致済み単体出力と bit 一致`, eq.map((e) => (e ? '512/512' : 'DIFF')).join(' '));
process.exit(eq.every(Boolean) ? 0 : 1);
