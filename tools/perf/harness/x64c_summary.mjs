// results/x64c/*_<tag>.jsonl を集計して markdown 表を出す。 node x64c_summary.mjs <tag> [期待署名 (既定 6b1696f0)]
import fs from 'node:fs';
const tag = process.argv[2], EXPECT = process.argv[3] || '6b1696f0';
const dir = new URL('../results/x64c/', import.meta.url).pathname;
const rd = (n) => { const f = `${dir}${n}_${tag}.jsonl`; return fs.existsSync(f) ? fs.readFileSync(f, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []; };
const med = (a) => { const b = [...a].sort((x, y) => x - y); return b.length % 2 ? b[b.length >> 1] : (b[b.length / 2 - 1] + b[b.length / 2]) / 2; };
const rng = (a, d = 1) => `${Math.min(...a).toFixed(d)}–${Math.max(...a).toFixed(d)}`;
const by = (rows, k) => { const m = new Map(); for (const r of rows) { const key = k(r); if (!m.has(key)) m.set(key, []); m.get(key).push(r); } return m; };
const sigs = new Set(); const errs = [];
const row = (cells) => '| ' + cells.join(' | ') + ' |';
const out = [];
const node = rd('node'), worker = rd('worker').filter((r) => { if (r.error) errs.push(r); return !r.error; });
const wl = rd('worklet').filter((r) => { if (r.error) errs.push(r); return !r.error; }), wn = rd('worklet-noclock').filter((r) => { if (r.error) errs.push(r); return !r.error; }), nat = rd('native');
for (const r of [...node, ...nat]) sigs.add(r.sig); for (const r of [...worker, ...wl, ...wn]) sigs.add(r.signature);
const cnt = (rows) => rows.length;
out.push(`### node (${node[0]?.node}) — x64c_core, 1 変種 1 プロセス, 20000 block 個別計時`, '', row(['変種', '反復', 'p50 µs (範囲)', 'p50 中央値', 'p99 µs 中央値', 'max µs (最大)', 'RTF@44.1k 中央値', 'load']), row(['---', '--:', '--:', '--:', '--:', '--:', '--:', '--:']));
for (const [v, rs] of by(node, (r) => r.v)) out.push(row([v, cnt(rs), rng(rs.map((r) => r.p50us)), med(rs.map((r) => r.p50us)).toFixed(2), med(rs.map((r) => r.p99us)).toFixed(1), Math.max(...rs.map((r) => r.maxus)).toFixed(0), med(rs.map((r) => r.rtf44)).toFixed(5), rng(rs.map((r) => r.load), 2)]));
out.push('', `### Chrome Dedicated Worker (${worker[0]?.ua?.match(/Chrome\/[\d.]+/)?.[0]}, v8 ${worker[0]?.v8})`, '', row(['変種', '反復', 'p50 µs (範囲)', 'p50 中央値', 'p99 µs 中央値', 'max µs (最大)', 'batch64 p50 µs 中央値', 'RTF@44.1k 中央値', 'compile ms (範囲)', 'load']), row(['---', '--:', '--:', '--:', '--:', '--:', '--:', '--:', '--:', '--:']));
for (const [v, rs] of by(worker, (r) => r.variant)) out.push(row([v, cnt(rs), rng(rs.map((r) => r.steady.p50 * 1000)), (med(rs.map((r) => r.steady.p50)) * 1000).toFixed(2), (med(rs.map((r) => r.steady.p99)) * 1000).toFixed(1), (Math.max(...rs.map((r) => r.steady.max)) * 1000).toFixed(0), (med(rs.map((r) => r.batch64.p50)) * 1000).toFixed(2), med(rs.map((r) => r.rtf44)).toFixed(5), rng(rs.map((r) => r.compileMs), 0), rng(rs.map((r) => r.loadStart), 2)]));
out.push('', '### Chrome 実 AudioWorklet — process() 内 wasm 1 block の所要 (SAB カウンタ時計; 3000 block 実時間駆動)', '', row(['変種', '反復', 'p50 µs (範囲)', 'p99 µs 中央値', 'p99.9 µs 中央値', 'max µs (最大)', '予算超過 (> 128f 時間) 合計', '> 1 ms 合計', '時計 0 tick の呼出 (時計 worker 停滞) 合計', 'bench 平均 µs/block (範囲, Date.now)', 'RTF@48k p50 中央値', 'load']), row(['---', '--:', '--:', '--:', '--:', '--:', '--:', '--:', '--:', '--:', '--:', '--:']));
for (const [v, rs] of by(wl, (r) => r.variant)) out.push(row([v, cnt(rs), rng(rs.map((r) => r.rt.durUs.p50)), med(rs.map((r) => r.rt.durUs.p99)).toFixed(1), med(rs.map((r) => r.rt.durUs.p999)).toFixed(1), Math.max(...rs.map((r) => r.rt.durUs.max)).toFixed(0), rs.reduce((a, r) => a + r.rt.overBudget, 0) + ` / ${rs.reduce((a, r) => a + r.rt.n, 0)}`, rs.reduce((a, r) => a + r.rt.over1ms, 0), rs.reduce((a, r) => a + (r.rt.zeroDur ?? 0), 0), rng(rs.map((r) => r.bench.meanUsPerBlock)), med(rs.map((r) => r.rt.rtfP50)).toFixed(5), rng(rs.map((r) => r.loadStart), 2)]));
if (wl.length) {
  const g = wl.map((r) => r.rt); out.push('', `AudioWorklet 駆動の実態 (全 ${wl.length} 実行): sampleRate ${[...new Set(g.map((x) => x.sampleRate))]} / 予算 ${g[0].budgetUs.toFixed(1)} µs / process() 入口間隔 p50 ${rng(g.map((x) => x.gapUs.p50), 0)} µs・max ${rng(g.map((x) => x.gapUs.max), 0)} µs (バースト駆動: ハードウェア buffer 単位) / 平均間隔 ${rng(g.map((x) => x.gapUs.mean), 0)} µs / 時計 ticks/µs: worklet 較正 ${rng(g.map((x) => x.ticksPerUs), 1)} vs 時計 worker 較正 ${rng(g.map((x) => x.clockWorkerTicksPerUs), 1)}`);
}
out.push('', '### Chrome AudioWorklet (時計 worker 無し対照; 500 block × 20 chunk の Date.now 平均)', '', row(['変種', '反復', 'bench 平均 µs/block (範囲)', 'RTF@48k 中央値']), row(['---', '--:', '--:', '--:']));
for (const [v, rs] of by(wn, (r) => r.variant)) out.push(row([v, cnt(rs), rng(rs.map((r) => r.bench.meanUsPerBlock)), med(rs.map((r) => r.bench.rtfMean)).toFixed(5)]));
out.push('', '### native x86-64 実機械語 (libottnative.so; ott_call 1 回 = processReplacing 128f)', '', row(['反復', 'p50 µs (範囲)', 'p99 µs 中央値', 'max µs (最大)', 'batch64 p50 µs 中央値', 'RTF@44.1k 中央値', 'load']), row(['--:', '--:', '--:', '--:', '--:', '--:', '--:']));
if (nat.length) out.push(row([nat.length, rng(nat.map((r) => r.p50us), 2), med(nat.map((r) => r.p99us)).toFixed(1), Math.max(...nat.map((r) => r.maxus)).toFixed(0), med(nat.map((r) => r.batch64p50us)).toFixed(2), med(nat.map((r) => r.rtf44)).toFixed(5), rng(nat.map((r) => r.load), 2)]));
const nm = med(nat.map((r) => r.p50us));
out.push('', '### wasm / native 比 (node の p50 中央値 ÷ native p50 中央値)', '', row(['変種', 'node ÷ native', 'Chrome Worker ÷ native']), row(['---', '--:', '--:']));
for (const [v, rs] of by(node, (r) => r.v)) { const w = worker.filter((r) => r.variant === v); out.push(row([v, (med(rs.map((r) => r.p50us)) / nm).toFixed(2) + '×', w.length ? (med(w.map((r) => r.steady.p50 * 1000)) / nm).toFixed(2) + '×' : '-'])); }
out.push('', `署名検査: 全 ${node.length + nat.length + worker.length + wl.length + wn.length} 実行の署名集合 = {${[...sigs]}} → ${sigs.size === 1 && sigs.has(EXPECT) ? 'PASS (期待 ' + EXPECT + ')' : 'FAIL (期待 ' + EXPECT + ')'}; 失敗実行 ${errs.length} 件`);
console.log(out.join('\n'));
