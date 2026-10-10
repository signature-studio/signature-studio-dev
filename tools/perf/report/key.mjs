import { readJsonl, group, summarize, f } from './agg.mjs';
const N = [...['node_ott_all', 'node_ott_wo', 'node_ott_tier', 'node_ott_extra'].flatMap((n) => readJsonl(n + '.jsonl'))];
const C = [...['chrome_ott_all', 'chrome_ott_tier', 'chrome_ott_wo', 'chrome_ott_lto'].flatMap((n) => readJsonl(n + '.jsonl'))];
const sn = new Map([...group(N, (r) => `${r.variant}|${r.mode}`)].map(([k, v]) => [k, summarize(v)]));
const sc = new Map([...group(C, (r) => `${r.variant}|${r.mode}`)].map(([k, v]) => [k, summarize(v)]));
const o0 = sn.get('o0|default');
console.log('variant | node p50 med / min / p99 / RTF44 / RTF48 / x o0 | chrome p50 / p99 / RTF44');
for (const v of ['o0', 'o0min', 'o1', 'o2', 'o3', 'os', 'oz', 'o2simd', 'o3simd', 'o2lto', 'o3lto', 'oslto', 'o2thinlto', 'o3thinlto', 'o2ltosimd', 'o3ltosimd', 'o3lto_m1flags', 'o2thr', 'o2thrsimd', 'o2fullnogc', 'o2fullgc', 'o2m1flags', 'wo_o2raw_none', 'wo_o2raw_O2', 'wo_o2raw_O3', 'wo_o2raw_O3conv', 'wo_o2raw_Oz', 'wo_o2rawsimd_O3', 'wo_o2rawsimd_none']) {
  const a = sn.get(v + '|default'), b = sc.get(v + '|default'); if (!a) continue;
  console.log(v, '|', f(a.p50, 4), f(a.p50min, 4), f(a.p99, 4), f(a.p50 / (128 / 44100 * 1000), 4), f(a.p50 / (128 / 48000 * 1000), 4), f(o0.p50 / a.p50, 1) + 'x', '|', b ? `${f(b.p50, 4)} ${f(b.p99, 4)} ${f(b.rtf44, 4)}` : '-', '| create node', f(a.createMs, 1));
}
for (const m of ['liftoff', 'tf']) for (const v of ['o0', 'o2', 'o2simd', 'o3', 'o2lto']) { const a = sn.get(`${v}|${m}`), b = sc.get(`${v}|${m}`); const d = sn.get(`${v}|default`); if (a) console.log(m, v, 'node p50', f(a.p50, 4), 'ratio to default', f(a.p50 / d.p50, 2), 'chrome', b ? f(b.p50, 4) : '-'); }
