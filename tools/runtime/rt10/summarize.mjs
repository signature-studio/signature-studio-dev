// RT-10 (#128): results/rt10_*.jsonl の集計 (min–max / median)。 node tools/runtime/rt10/summarize.mjs
import fs from 'node:fs';
const RES = new URL('./results/', import.meta.url).pathname;
const rd = (e) => { const f = RES + `rt10_${e}.jsonl`; return fs.existsSync(f) ? fs.readFileSync(f, 'utf8').trim().split('\n').map((l) => JSON.parse(l)) : []; };
const med = (v) => { const s = [...v].sort((x, y) => x - y); const n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };
const rng = (v, d = 0) => (v.length ? `${Math.min(...v).toFixed(d)}–${Math.max(...v).toFixed(d)} (med ${med(v).toFixed(d)}, n=${v.length})` : 'n/a');
const grp = (rows, key) => { const m = new Map(); for (const r of rows) { const k = key(r); (m.get(k) || m.set(k, []).get(k)).push(r); } return m; };
const ok = (rows) => rows.filter((r) => r.ok);
const loadR = (rows) => rng(rows.map((r) => r.load), 2);

console.log('## cold (fresh profile, HTTP cache cold)');
for (const [k, rs] of grp(ok(rd('cold')), (r) => `${r.flags}/${r.mode}`)) {
  console.log(`- ${k}: load ${loadR(rs)}\n  fetch+compile ms ${rng(rs.map((r) => r.phases.fetchCompileMs))}` +
    (rs[0].mode === 'bytes' ? `\n    fetchBody ms ${rng(rs.map((r) => r.phases.fetchBodyMs))}; compileOnly ms ${rng(rs.map((r) => r.phases.compileOnlyMs))}` : '') +
    `\n  instantiate ms ${rng(rs.map((r) => r.phases.firstInstantiateMs), 1)}; boot ms ${rng(rs.map((r) => r.phases.firstBootMs))}; total→boot done ms ${rng(rs.map((r) => r.phases.totalToFirstBootDoneMs))}` +
    `\n  renderer RSS end/HWM MB ${rng(rs.map((r) => r.rss?.rssMB))} / ${rng(rs.map((r) => r.rss?.hwmMB))}; units_run ${[...new Set(rs.map((r) => r.boots[0].units_run))]} stage ${[...new Set(rs.map((r) => r.boots[0].stage))]} threw ${[...new Set(rs.map((r) => r.boots[0].threw))]} getmem/freemem ${[...new Set(rs.map((r) => r.boots[0].getmem + '/' + r.boots[0].freemem))]}`);
}
console.log('## warm (same profile, immutable)');
for (const [k, rs] of grp(ok(rd('warm')), (r) => `load#${r.load_no}${r.restart ? '(restart)' : ''}`)) {
  console.log(`- ${k}: fetch+compile ms ${rng(rs.map((r) => r.phases.fetchCompileMs))}; transferSize ${[...new Set(rs.map((r) => r.phases.resource?.transferSize))]}; boot ms ${rng(rs.map((r) => r.phases.firstBootMs))}; load ${loadR(rs)}`);
}
console.log('## bw (compressed bytes paced by server)');
for (const [k, rs] of grp(ok(rd('bw')), (r) => `${r.mbps}Mbps`)) {
  console.log(`- ${k}: fetch+compile ms ${rng(rs.map((r) => r.phases.fetchCompileMs))}; total→boot done ms ${rng(rs.map((r) => r.phases.totalToFirstBootDoneMs))}; resource.duration ms ${rng(rs.map((r) => r.phases.resource?.durationMs))}; load ${loadR(rs)}`);
}
console.log('## tier (same Module, N instances sequentially)');
for (const [k, rs] of grp(ok(rd('tier')), (r) => r.flags)) {
  const n = Math.max(...rs.map((r) => r.boots.length));
  const per = [];
  for (let i = 0; i < n; i++) per.push(`#${i + 1} boot ${rng(rs.map((r) => r.boots[i]?.bootMs).filter((x) => x != null))} inst ${rng(rs.map((r) => r.boots[i]?.instantiateMs).filter((x) => x != null), 1)}`);
  console.log(`- ${k}: load ${loadR(rs)}\n  ` + per.join('\n  '));
}
console.log('## soak (instance create → boot → drop loop; 180 s と 540 s)');
for (const r of [...rd('soak'), ...rd('soak_long')]) {
  if (!r.ok) { console.log('- FAILED', r.error); continue; }
  const s = r.soak; const q = (a, b) => s.slice(a, b);
  const bt = (x) => rng(x.map((e) => e.bootMs), 0);
  console.log(`- flags ${r.flags} soakSec ${r.soakSec} load@start ${r.load.toFixed(2)}: cycles ${s.length}; boot ms first5 ${bt(q(0, 5))}; last5 ${bt(q(-5))}; all ${bt(s)}`);
  console.log(`  units_run ${[...new Set(s.map((e) => e.units_run))]} stage ${[...new Set(s.map((e) => e.stage))]}; instantiate ms ${rng(s.map((e) => e.instantiateMs), 1)}`);
  const W = Math.max(30000, Math.round(r.soakSec * 1000 / 6));
  const buckets = [];
  for (let t = 0; t < r.soakSec * 1000; t += W) {
    const b = s.filter((e) => e.t >= t && e.t < t + W);
    const rr = (r.rssSeries || []).filter((e) => e.t >= t && e.t < t + W);
    if (b.length) buckets.push(`${Math.round(t / 1000)}–${Math.round((t + W) / 1000)}s: n=${b.length} boot med ${med(b.map((e) => e.bootMs)).toFixed(0)} ms; RSS ${rr.length ? Math.min(...rr.map((e) => e.rssMB)).toFixed(0) + '–' + Math.max(...rr.map((e) => e.rssMB)).toFixed(0) : 'n/a'} MB`);
  }
  console.log('  ' + buckets.join('\n  '));
  const rs = r.rssSeries || [];
  console.log(`  renderer RSS MB: first ${rs[0]?.rssMB.toFixed(0)}, min ${Math.min(...rs.map((e) => e.rssMB)).toFixed(0)}, max ${Math.max(...rs.map((e) => e.rssMB)).toFixed(0)}, end ${rs.at(-1)?.rssMB.toFixed(0)}; HWM end ${rs.at(-1)?.hwmMB.toFixed(0)}; samples ${rs.length}`);
}
