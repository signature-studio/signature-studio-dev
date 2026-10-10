import { readJsonl, group, summarize, f } from './agg.mjs';
const src = process.argv[2] || 'node';
for (const kind of ['a1', 'a2']) {
  const rows = readJsonl(`${src}_m5_${kind}.jsonl`);
  const g = group(rows, (r) => `${r.variant}|${r.mode}`);
  const S = new Map([...g].map(([k, v]) => [k, summarize(v)]));
  console.log(`\n#### M5 ${kind === 'a1' ? 'waveshaper (function_6a7540)' : 'distortion (function_6a2fb0)'} — ${src}, 128 サンプル/call, 64 call バッチ平均\n`);
  console.log('| variant | tier | wasm B | µs / 128 sample | RTF@44.1k | sig |'); console.log('|---|---|--:|--:|--:|---|');
  for (const mode of ['default', 'liftoff', 'tf']) for (const v of ['o0', 'o1', 'o2', 'o3', 'o1simd', 'o2simd', 'o3simd']) {
    const s = S.get(`${v}|${mode}`); if (!s) continue;
    console.log(`| ${v} | ${mode} | ${s.wasmBytes ?? '-'} | ${f(s.p50min * 1000, 3)} (med ${f(s.p50 * 1000, 3)}) | ${s.rtf44.toExponential(2)} | ${s.sigs.join('/')} |`);
  }
}
