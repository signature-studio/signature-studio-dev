// multi_x64c.mjs — x64c lowbase module を 1 プロセスに N 個 (+ 別 base の module も混在) 同時ロードし、標準 scenario の出力が全 instance 同一かつ
//   matrix.py が native 機械語と bit 一致を確認済みの単体出力 (scen2_wasm の std) と一致することを示す。メモリ合計を /proc/self/status で計測。
//   usage: LB_BASE=<base0> node multi_x64c.mjs --mods a.cjs:BASE:ARENA,b.cjs:BASE:ARENA,... --ref std_ref.json [--out r.json]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const mods = arg('mods').split(',').map((s) => { const [cjs, base, arena] = s.split(':'); return { cjs, base: Number(base), arena: Number(arena) }; });
const ref = JSON.parse(fs.readFileSync(arg('ref'), 'utf8'));
const st = () => { const t = fs.readFileSync('/proc/self/status', 'utf8'); const g = (k) => Number(t.match(new RegExp(k + ':\\s+(\\d+) kB'))[1]) / 1024; return { rss: +g('VmRSS').toFixed(0), vmdata: +g('VmData').toFixed(0) }; };
const m0 = st();
const n = 256, f32b = (v) => { const f = new Float32Array(1); f[0] = v; return BigInt(new Uint32Array(f.buffer)[0]); };
const insts = [];
for (const m of mods) {
  const mod = await (await import(m.cjs)).default();
  mod._ott_data_install();
  const run = (va, a, x = []) => BigInt.asUintN(64, mod._ott_run(m.base + (va - 0x180000000), BigInt(a[0] ?? 0), BigInt(a[1] ?? 0), BigInt(a[2] ?? 0), BigInt(a[3] ?? 0), BigInt(x[0] ?? 0), BigInt(x[1] ?? 0), BigInt(x[2] ?? 0), BigInt(x[3] ?? 0)));
  insts.push({ ...m, mod, run });
}
const m1 = st();
const outs = [];
for (const I of insts) {
  const OBJ = I.arena + 0x10000, IN_A = I.arena + 0x20000, OU_A = I.arena + 0x30000, BUF = I.arena + 0x40000;
  const inp = new Float32Array(n * 2);
  for (let i = 0; i < n; i++) { inp[i] = Math.fround(Math.sin(i * 0.05) * 0.7 + Math.sin(i * 0.011) * 0.3); inp[n + i] = Math.fround(Math.cos(i * 0.13) * 0.5); }
  I.run(0x18011d400, [OBJ, 0]); for (let i = 0; i < 19; i++) I.run(0x180120af0, [OBJ, i], [0, 0, f32b(0.5)]);
  I.run(0x180120800, [OBJ]);
  const U8 = I.mod.HEAPU8, U32 = I.mod.HEAPU32, F32 = I.mod.HEAPF32;
  U32[IN_A / 4] = BUF; U32[IN_A / 4 + 2] = BUF + n * 4; U32[OU_A / 4] = BUF + n * 8; U32[OU_A / 4 + 2] = BUF + n * 12;
  F32.set(inp, BUF / 4);
  I.run(0x18011ec20, [OBJ, IN_A, OU_A, n]);
  outs.push(Array.from(I.mod.HEAPU32.subarray((BUF + n * 8) / 4, (BUF + n * 8) / 4 + 2 * n)));
}
const m2 = st();
const refOut = ref.outs[0];
const eqRef = outs.map((o) => o.every((v, i) => v === refOut[i]));
const mem = insts.map((I) => I.mod.HEAPU8.length / 1048576);
console.log(`INFO x64c modules=${insts.length} bases=${insts.map((I) => '0x' + I.base.toString(16)).join(',')} linear MiB=${mem.join('/')} sum=${mem.reduce((a, b) => a + b, 0)}; VmData ${m0.vmdata}→${m1.vmdata}→${m2.vmdata} MB, RSS ${m0.rss}→${m2.rss} MB`);
console.log(`${eqRef.every(Boolean) ? 'OK  ' : 'FAIL'} X1 x64c ${insts.length} module (base 混在) の標準 scenario 出力 512 cell が全て native 一致済み単体出力と bit 一致`, eqRef.map((e) => e ? '512/512' : 'DIFF').join(' '));
const res = { modules: insts.length, linear_mib: mem, linear_sum_mib: mem.reduce((a, b) => a + b, 0), vm: { m0, m1, m2 }, equal_to_native_verified_ref: eqRef };
if (arg('out')) fs.writeFileSync(arg('out'), JSON.stringify(res, null, 1));
process.exit(eqRef.every(Boolean) ? 0 : 1);
