// OTT / M5 の node・Chrome 結果から markdown 表を出力
import { readJsonl, group, summarize, f } from './agg.mjs';
import fs from 'node:fs';
import zlib from 'node:zlib';
const W = new URL('../work/', import.meta.url).pathname;
const src = process.argv[2] || 'node';   // node | chrome
const files = src === 'node' ? ['node_ott_all.jsonl', 'node_ott_wo.jsonl', 'node_ott_tier.jsonl', 'node_ott_extra.jsonl'] : ['chrome_ott_all.jsonl', 'chrome_ott_tier.jsonl', 'chrome_ott_wo.jsonl', 'chrome_ott_lto.jsonl'];
const rows = files.flatMap(readJsonl);
const g = group(rows, (r) => `${r.variant}|${r.mode}`);
const S = new Map([...g].map(([k, v]) => [k, summarize(v)]));
// 同一変種が複数 jsonl に在る場合 (o2 等) は上で併合される
const size = (v) => { try { return fs.statSync(`${W}ott/${v}/ott.wasm`).size; } catch { return NaN; } };
const gz = (v) => { try { return zlib.gzipSync(fs.readFileSync(`${W}ott/${v}/ott.wasm`), { level: 9 }).length; } catch { return NaN; } };
const base = S.get('o0|default');
function table(title, names, mode = 'default') {
  console.log(`\n#### ${title}\n`);
  console.log('| variant | wasm B | gzip B | p50 ms/128f | p99 ms | RTF@44.1k (p50) | RTF@44.1k (p99) | OTT instances/core | speedup vs o0 | sig |');
  console.log('|---|--:|--:|--:|--:|--:|--:|--:|--:|---|');
  for (const n of names) {
    const s = S.get(`${n}|${mode}`); if (!s) continue;
    console.log(`| ${n}${mode !== 'default' ? ' (' + mode + ')' : ''} | ${size(n)} | ${gz(n)} | ${f(s.p50, 4)}${s.batched ? '†' : ''} | ${f(s.p99, 4)} | ${f(s.rtf44, 4)} | ${f(s.rtf44p99, 3)} | ${f(1 / s.rtf44, 1)} | ${base ? f(base.p50 / s.p50, 2) + '×' : '-'} | ${s.sigs.length === 1 ? s.sigs[0] : 'MISMATCH ' + s.sigs.join('/')} |`);
  }
}
table('A. emcc -O 水準 (SIMD 無し, gc-sections, min exports)', ['o0', 'o0min', 'o1', 'o2', 'o3', 'os', 'oz']);
table('B. -msimd128 (C helper の SIMD 化)', ['o0', 'o0simd', 'o1', 'o1simd', 'o2', 'o2simd', 'o3', 'o3simd', 'os', 'ossimd']);
table('C0. LTO 深掘り (helper の関数呼出 inline 化: processReplacing の call 数 715→1)', ['o2', 'o2lto', 'o3lto', 'o3ltosimd', 'oslto', 'o2thinlto', 'o3thinlto', 'o3lto_m1flags', 'o3lto_wasmopt']);
table('C. LTO / gc-sections / export 数 / M1 定型 CFLAGS / threads', ['o2', 'o2lto', 'o3lto', 'o2ltosimd', 'o2fullnogc', 'o2fullgc', 'o2m1flags', 'o2thr', 'o2thrsimd']);
for (const inp of ['o2raw', 'o3raw', 'o2rawsimd']) {
  table(`D. wasm-opt (binaryen v133) 水準比較 — 入力 ${inp} (clang のみ, binaryen 未通過)`, [`wo_${inp}_none`, `wo_${inp}_O1`, `wo_${inp}_O2`, `wo_${inp}_O3`, `wo_${inp}_Os`, `wo_${inp}_Oz`, `wo_${inp}_O4`, `wo_${inp}_O2conv`, `wo_${inp}_O3conv`, `wo_${inp}_O3convfl`]);
}
for (const m of ['liftoff', 'tf']) table(`E. tier 強制 (${m})`, ['o0', 'o2', 'o2simd', 'o3', 'o2lto'], m);
