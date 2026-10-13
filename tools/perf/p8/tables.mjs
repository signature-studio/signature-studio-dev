// results/p8.jsonl → results/TABLES.md (自動生成)。使い方: node tables.mjs [--tag <label>]
import fs from 'node:fs'; import path from 'node:path'; import zlib from 'node:zlib'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url)); const RES = path.join(HERE, 'results'); const W = path.join(HERE, 'work');
const ALL = fs.readFileSync(path.join(RES, 'p8.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
const med = (a) => { const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };
const RTS = [...new Set(ALL.map((r) => r.runtime).filter(Boolean))];
for (const r of ALL) if (!r.runtime) r.runtime = (/127\.0\.0\.1/.test(String(r.error)) ? RTS.find((x) => x.startsWith('chrome')) : RTS.find((x) => x.startsWith('node'))) ?? 'unknown'; // 旧版は error 行に runtime が無い
let rows = ALL;
const grp = (mode) => { const m = new Map(); for (const r of rows.filter((x) => x.mode === mode)) { const k = `${r.cfg}|${r.N}`; (m.get(k) ?? m.set(k, []).get(k)).push(r); } return m; };
const rng = (v, key, d = 2) => { const a = v.filter((x) => x[key] != null).map((x) => x[key]); if (!a.length) return '-'; const lo = Math.min(...a), hi = Math.max(...a); return `${med(a).toFixed(d)} (${lo.toFixed(d)}–${hi.toFixed(d)})`; };
const MB = (b) => (b / 1048576).toFixed(1);
let o = ['<!-- 自動生成: node tools/perf/p8/tables.mjs (入力 results/p8.jsonl)。人手編集禁止 -->', '', '# P8 TABLES', ''];
const envLine = () => rows[0] ? `${rows[0].runtime}, ${rows[0].cpus} cores, loadavg(各 run 開始時の 1 分値) ${Math.min(...rows.filter((r) => r.loadavg?.length).map((r) => r.loadavg[0]))}〜${Math.max(...rows.filter((r) => r.loadavg?.length).map((r) => r.loadavg[0]))}` : '';
for (const rt of [...new Set(ALL.map((r) => r.runtime))]) {
  rows = ALL.filter((r) => r.runtime === rt);
  o.push(`# 実行系: ${rt}`, '', envLine(), '');
{ // steady
  const m = grp('steady'); const cfgs = [...new Set([...m.keys()].map((k) => k.split('|')[0]))]; const Ns = [...new Set([...m.keys()].map((k) => +k.split('|')[1]))].sort((a, b) => a - b);
  for (const kind of ['', '_light']) {
    const cs = cfgs.filter((c) => (kind ? c.endsWith('_light') : !c.endsWith('_light'))); if (!cs.length) continue;
    o.push(`## 定常 µs / 128f ブロック (${kind ? '軽量カーネル NST=1' : '標準カーネル NST=32'}; 各セル = 独立プロセス間の p50 の中央値 (min–max)、比 = 同 N の static_based${kind} 比)`, '');
    o.push(`| 構成 | ${Ns.map((n) => `N=${n}`).join(' | ')} |`, `|---|${Ns.map(() => '--:').join('|')}|`);
    for (const c of cs) o.push(`| ${c} | ${Ns.map((n) => { const v = m.get(`${c}|${n}`); if (!v) return '-'; const b = m.get(`static_based${kind}|${n}`) ?? m.get(`sep_based${kind}|${n}`); const ratio = b ? ` ×${(med(v.map((x) => x.us_per_block)) / med(b.map((x) => x.us_per_block))).toFixed(3)}` : ''; return `${rng(v, 'us_per_block', kind ? 3 : 2)}${ratio}`; }).join(' | ')} |`);
    o.push('');
  }
}
{ // startup
  const m = grp('startup'); const cfgs = [...new Set([...m.keys()].map((k) => k.split('|')[0]))]; const Ns = [...new Set([...m.keys()].map((k) => +k.split('|')[1]))].sort((a, b) => a - b);
  for (const [key, title] of [['load_ms', 'load = compile+instantiate(+init / dlopen) 合計 ms'], ['first_block_ms', '初回 chain 1 ブロック ms (lazy 初回呼出 stall)']]) {
    o.push(`## 起動: ${title} (独立プロセス n 回の中央値 (min–max))`, '', `| 構成 | ${Ns.map((n) => `N=${n}`).join(' | ')} |`, `|---|${Ns.map(() => '--:').join('|')}|`);
    for (const c of cfgs) o.push(`| ${c} | ${Ns.map((n) => { const v = m.get(`${c}|${n}`); return v ? (v[0].error ? 'ERR' : rng(v, key, 1)) : '-'; }).join(' | ')} |`);
    o.push('');
  }
  o.push('## dlopen 内訳 ms (dyn_*): main instantiate / 1 本目 / 2 本目以降 p50', '', '| 構成 | N | main instantiate | dlopen 1 本目 | dlopen 2 本目以降 p50 | dlopen 合計 |', '|---|--:|--:|--:|--:|--:|');
  for (const [k, v] of m) if (k.startsWith('dyn')) o.push(`| ${k.split('|')[0]} | ${k.split('|')[1]} | ${rng(v, 'main_instantiate', 1)} | ${rng(v, 'dlopen_first', 1)} | ${rng(v, 'dlopen_rest_p50', 2)} | ${rng(v, 'dlopen_sum', 1)} |`);
  o.push('', '## compile / instantiate 内訳 ms (static_*, sep_*)', '', '| 構成 | N | compile 合計 | instantiate 合計 |', '|---|--:|--:|--:|');
  for (const [k, v] of m) if (!k.startsWith('dyn')) o.push(`| ${k.split('|')[0]} | ${k.split('|')[1]} | ${rng(v, 'compile', 1)} | ${rng(v, 'instantiate', 1)} |`);
  o.push('');
}
{ // memory
  const m = grp('memory'); o.push('## メモリ (N 個 load + 1 ブロック後; 独立プロセス 1 回)', '', '| 構成 | N | WebAssembly.Memory 本数 | 予約 memory 合計 MiB | RSS 増分 MiB | プロセス HWM MiB |', '|---|--:|--:|--:|--:|--:|');
  for (const [k, v] of m) { const r = v[0]; o.push(r.error ? `| ${r.cfg} | ${r.N} | ERR: ${String(r.error).replace(/\|/g, '/').slice(0, 120)} | | | |` : `| ${r.cfg} | ${r.N} | ${r.memories} | ${MB(r.wasm_memory_bytes)} | ${MB(r.rss_delta_bytes)} | ${MB(r.hwm_bytes)} |`); }
  o.push('');
}
{ // derived
  const st = grp('steady'), su = grp('startup'), me = grp('memory'); const g = (m, c, n, key) => { const v = m.get(`${c}|${n}`); if (!v) return null; const a = v.filter((x) => x[key] != null).map((x) => x[key]); return a.length ? med(a) : null; };
  o.push('### 派生値 (上の表の中央値から算出。式は各行に明記)', '', '| 項目 | 値 |', '|---|--:|');
  for (const N of [16, 64]) {
    const sep = g(st, 'sep_based_light', N, 'us_per_block'), nc = g(st, 'sep_based_nocopy_light', N, 'us_per_block'), dh = g(st, 'dyn_hid_light', N, 'us_per_block');
    if (sep != null && nc != null && dh != null) o.push(`| 境界コスト/plugin/ブロック N=${N} (軽量カーネル): plugin 間コピー 1 KiB = (sep_based−sep_based_nocopy)/N | ${((sep - nc) / N * 1000).toFixed(0)} ns |`, `| 同: JS→wasm 呼出 1 回 = (sep_based_nocopy−dyn_hid)/N | ${((nc - dh) / N * 1000).toFixed(0)} ns |`);
  }
  for (const c of ['sep_based', 'sep_based_shared', 'dyn_hid', 'dyn_def']) { const a = g(su, c, 1, 'load_ms'), b = g(su, c, 64, 'load_ms'); if (a != null && b != null) o.push(`| 起動/plugin ms (load(N=64)−load(N=1))/63: ${c} | ${((b - a) / 63).toFixed(2)} |`); }
  for (const c of ['sep_based', 'sep_based_shared', 'sep_abs_lo', 'sep_abs_hi', 'dyn_hid']) { const a = g(me, c, 1, 'rss_delta_bytes'), b = g(me, c, 128, 'rss_delta_bytes'); if (a != null && b != null) o.push(`| RSS/plugin MiB (RSS増分(N=128)−RSS増分(N=1))/127: ${c} | ${((b - a) / 127 / 1048576).toFixed(2)} |`); }
  o.push('');
}
}
for (const [f, title] of [['p8_diag.jsonl', '## 診断: Chrome の tier を固定した定常 µs/ブロック (steady, `P8_JSFLAGS` で `--no-liftoff`=TurboFan のみ / `--liftoff-only`)'], ['p8_limit.jsonl', '## 診断: Chrome の Memory 本数上限 (memory モード; OK/ERR)']]) {
  const p = path.join(RES, f); if (!fs.existsSync(p)) continue; const d = fs.readFileSync(p, 'utf8').trim().split('\n').map((l) => JSON.parse(l));
  o.push(title, '', f.includes('diag') ? '| jsflags | 構成 | N | µs/ブロック (p50, 1 回) | 対 static_based |\n|---|---|--:|--:|--:|' : '| 構成 | N | 結果 |\n|---|--:|---|');
  for (const r of d) o.push(f.includes('diag') ? `| ${r.jsflags} | ${r.cfg} | ${r.N} | ${r.us_per_block.toFixed(2)} | ×${(r.us_per_block / d.find((x) => x.jsflags === r.jsflags && x.cfg === 'static_based' && x.N === r.N).us_per_block).toFixed(3)} |` : `| ${r.cfg} | ${r.N} | ${r.error ? 'ERR ' + String(r.error).split('\n')[0].slice(-70) : 'OK (Memory ' + r.memories + ' 本)'} |`);
  o.push('');
}
{ // sizes
  o.push('## wasm サイズ (B)', '', '(合成カーネルは 256 関数が近似反復のため圧縮率は実 lift wasm の値ではない。raw のみ参照)', '', '| ファイル | raw | gzip-9 | brotli-11 |', '|---|--:|--:|--:|');
  for (const f of ['static_based_1', 'static_based_16', 'sep_abs_hi', 'sep_based', 'side_def', 'side_hid', 'dyn_main'].map((x) => x + '.wasm')) { const p = path.join(W, f); if (!fs.existsSync(p)) continue; const b = fs.readFileSync(p); o.push(`| ${f} | ${b.length} | ${zlib.gzipSync(b, { level: 9 }).length} | ${zlib.brotliCompressSync(b, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 11, [zlib.constants.BROTLI_PARAM_SIZE_HINT]: b.length } }).length} |`); }
  o.push('');
}
fs.writeFileSync(path.join(RES, 'TABLES.md'), o.join('\n')); console.log(o.join('\n'));
