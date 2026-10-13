// perf gate 判定 (相対指標のみ)。 node judge.mjs <bench.jsonl> [--load <loadavg>]
// bench.jsonl: ott_x64c_bench.mjs の出力 JSON 行 + build の "[x64c] <v> <bytes> B" 行から作った {"v","bytes"} 行
// env: GATE_SIG (既定 6b1696f0) / GATE_MIN_O0_O2 / GATE_MIN_O3LTO_O2 / GATE_MAX_O3LTO_O2 / GATE_MAX_BYTES_<V>
import fs from 'node:fs';
const E = (k, d) => (process.env[k] !== undefined ? Number(process.env[k]) : d);
const SIG = process.env.GATE_SIG || '6b1696f0';
const TH = {
  minO0O2: E('GATE_MIN_O0_O2', 3.0),      // o0 p50 / o2 p50 の下限 (実測 5.3〜5.9)
  minO2O3lto: E('GATE_MIN_O2_O3LTO', 0.9), // o2 p50 / o3lto p50 の下限 = LTO が退行しない (実測 1.15〜1.29)
  maxO2O3lto: E('GATE_MAX_O2_O3LTO', 2.0), // 同上限: 超えたら計測異常 (o2 側のスパイク) として FAIL
  bytes: { o0: E('GATE_MAX_BYTES_O0', 1200000), o2: E('GATE_MAX_BYTES_O2', 810000), o3lto: E('GATE_MAX_BYTES_O3LTO', 780000) },
};
const rows = fs.readFileSync(process.argv[2], 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
const med = (a) => { const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };
const V = {};
for (const r of rows) {
  if (r.bytes !== undefined) { (V[r.v] ??= { p50: [], sigs: [] }).bytes = r.bytes; continue; }
  const v = r.f.replace(/\.cjs$/, ''); const o = (V[v] ??= { p50: [], sigs: [] });
  o.p50.push(r.p50us); o.sigs.push(r.sig); (o.nz ??= []).push(r.nonzeroOut);
}
const checks = [];
const chk = (name, ok, detail) => checks.push({ name, ok, detail });
for (const v of ['o0', 'o2', 'o3lto']) {
  const o = V[v]; if (!o || !o.p50.length) { chk(`${v}: 計測あり`, false, '行なし'); continue; }
  chk(`${v}: 署名 == ${SIG} (全 ${o.sigs.length} 反復)`, o.sigs.every((s) => s === SIG), [...new Set(o.sigs)].join(','));
  chk(`${v}: 出力非ゼロ cell == 256`, o.nz.every((n) => n === 256), [...new Set(o.nz)].join(','));
  chk(`${v}: wasm bytes <= ${TH.bytes[v]}`, o.bytes <= TH.bytes[v], `${o.bytes}`);
}
if (['o0', 'o2', 'o3lto'].every((v) => V[v]?.p50.length)) {
  const m = Object.fromEntries(['o0', 'o2', 'o3lto'].map((v) => [v, med(V[v].p50)]));
  const r1 = m.o0 / m.o2, r2 = m.o2 / m.o3lto;
  chk(`o0/o2 p50 比 >= ${TH.minO0O2}`, r1 >= TH.minO0O2, r1.toFixed(2));
  chk(`o2/o3lto p50 比 in [${TH.minO2O3lto}, ${TH.maxO2O3lto}]`, r2 >= TH.minO2O3lto && r2 <= TH.maxO2O3lto, r2.toFixed(2));
  console.log(`median p50 us: o0 ${m.o0} / o2 ${m.o2} / o3lto ${m.o3lto} (参考値・判定は比のみ)`);
}
for (const c of checks) console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name}  [${c.detail}]`);
const bad = checks.filter((c) => !c.ok).length;
console.log(`[perf_gate] ${bad ? 'FAIL' : 'PASS'} (${checks.length - bad}/${checks.length})`);
process.exit(bad ? 1 : 0);
