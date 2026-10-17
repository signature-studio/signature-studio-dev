// shimx リンク版 M11 の起動ハーネス + shimx 呼出トレース収集 (CAB-166)。
//   node run_trace.mjs <m11_sx_*.cjs> [--out DIR]
// 環境変数 SHIMX_TRACE=1 → shimx_set_trace(1) (shimx の GetProcAddress miss / LoadLibrary 失敗等を stderr へ)。
// trace ビルド (sxt_* export あり) の場合は shim 名・回数・初回呼出 unit・unit 別集計・停止直前の呼出列を JSON 化する。
import fs from 'fs';
import path from 'path';
import { execFileSync } from 'child_process';

const M11 = path.resolve(new URL('../', import.meta.url).pathname);
const cjs = path.resolve(process.argv[2]);
const outDir = process.argv.includes('--out') ? process.argv[process.argv.indexOf('--out') + 1] : path.dirname(cjs);
const tag = path.basename(cjs).replace(/\.cjs$/, '');
const m2 = await import(cjs);
const stderrLines = [];
const trace = process.env.SHIMX_TRACE;
const mod = await (m2.default || m2)({
  printErr: (s) => { stderrLines.push(String(s)); },
  preRun: [(m) => { if (trace !== undefined) m.ENV.SHIMX_TRACE = trace; }],
});
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
// 実測: Emscripten の ENV を preRun で設定しても shimx の getenv("SHIMX_TRACE") には届かない (environ 初期化が先行) ため export で明示 ON
if (trace === '1') mod._shimx_set_trace(1);
const traceFile = process.env.SHIMX_TRACE_FILE;   // MEMFS 上のパス。node の環境変数は guest の getenv に届かないため export で渡す
if (traceFile && mod._shimx_set_trace_file) mod.ccall('shimx_set_trace_file', 'number', ['string'], [traceFile]);
if (process.env.M11_TRACE === '1') mod._m11_set_trace(1);
if (process.env.SXT_PRINT === '1' && mod._sxt_set_print) mod._sxt_set_print(1);

let rc = null, threw = null, dllmain_done = false, stack = null;
try {
  rc = mod._m11_boot_enter(0n, 1n);
} catch (e) {
  if (e && e.m11_dllmain_done !== undefined) { rc = BigInt(e.m11_dllmain_done); dllmain_done = true; }
  else { threw = (e && e.message) || String(e); stack = e && e.stack ? e.stack.split('\n').slice(0, 14).join('\n') : null; }
}
if (stack) {   // wasm-function[N] を export 名で注釈 (--export-all のため大半が名前を持つ)
  try {
    const ex = execFileSync('wasm-objdump', ['-x', '-j', 'Export', cjs + '.wasm'], { encoding: 'utf8', maxBuffer: 1 << 28 });
    const names = {};
    for (const m of ex.matchAll(/- func\[(\d+)\] <([^>]*)>/g)) names[m[1]] = m[2];
    stack = stack.replace(/wasm-function\[(\d+)\]/g, (_, i) => `wasm-function[${i}]<${names[i] || '?'}>`);
  } catch (_) {}
}
const num = (f) => { try { return Number(f()); } catch (_) { return null; } };
// #5855 (SHX-T61) 計装: IR に @fx61_buf があるときだけ読む。上限超えの trap 後でも wasm メモリから読める
const fx61 = typeof mod._fx61_count === 'function'
  ? { count: num(mod._fx61_count), self: num(mod._fx61_self), c4c: num(mod._fx61_c4c), c48: num(mod._fx61_c48) }
  : null;
// #5855 (SHX-T61 次段): 親 function_448490 の外側 loop 入口の計装 (IR に @fx61b_buf があるときだけ)
const fx61b = typeof mod._fx61b_count === 'function'
  ? { count: num(mod._fx61b_count), lim: num(mod._fx61b_lim), idx: num(mod._fx61b_idx), idx2: num(mod._fx61b_idx2) }
  : null;
const initCount = mod.HEAPU32[(0x11eac98 + Number(process.env.M11_LB_BASE || 0)) >> 2];
const units = [];
const stubs = [];
for (let i = 0; i < (num(mod._m11_stub_uniq) || 0); i++) stubs.push(mod.UTF8ToString(mod._m11_stub_name(i)) + ':' + mod._m11_stub_count(i));
const res = {
  variant: tag, shimx_trace_env: trace ?? null,
  boot_stage: num(mod._m11_boot_stage), init_count: num(mod._m11_init_count), init_count_var: initCount,
  units_total: num(mod._m11_units_total), units_run: num(mod._m11_units_run),
  va_calls: num(mod._m11_va_calls), va_used: num(mod._m11_va_used),
  icall_ok: num(mod._m11_icall_ok), icall_miss: num(mod._m11_icall_miss),
  dllmain_done, longjmp_hit: num(mod._m11_longjmp_hit), boot_rc: rc === null ? null : String(rc), threw, stack, fx61, fx61b,
  m11_stub_total: num(mod._m11_stub_total), m11_stub_hits: stubs,
  last_stderr: stderrLines.slice(-12),
};

if (typeof mod._sxt_n === 'function') {
  const n = mod._sxt_n();
  const calls = [];
  for (let i = 0; i < n; i++) {
    const c = mod._sxt_count(i);
    if (!c) continue;
    const fu = mod._sxt_first_unit(i);
    calls.push({ name: mod.UTF8ToString(mod._sxt_name(i)), gui: mod._sxt_gui(i), count: c, first_unit: fu,
                 first_unit_va: fu > 0 ? '0x' + (mod._m11_unit_va(fu - 1) + 0).toString(16) : null,
                 last_unit: mod._sxt_last_unit(i), first_seq: mod._sxt_first_seq(i) });
  }
  calls.sort((a, b) => a.first_seq - b.first_seq);
  const L = mod._sxt_log_n();
  const perUnit = {};
  const tail = [];
  const names = [];
  for (let i = 0; i < n; i++) names.push(mod.UTF8ToString(mod._sxt_name(i)));
  for (let k = 0; k < L; k++) {
    const v = mod._sxt_log_at(k); const idx = v >>> 16, unit = v & 0xffff;
    const u = (perUnit[unit] ||= { calls: 0, distinct: new Set() });
    u.calls++; u.distinct.add(idx);
  }
  for (let k = Math.max(0, L - 40); k < L; k++) { const v = mod._sxt_log_at(k); tail.push({ seq: k, unit: v & 0xffff, name: names[v >>> 16] }); }
  res.trace = {
    wrappers: n, total_calls: L, dropped: mod._sxt_dropped(),
    distinct_called: calls.length,
    distinct_gui_called: calls.filter((c) => c.gui).length,
    calls,
    per_unit: Object.fromEntries(Object.entries(perUnit).map(([u, v]) => [u, { calls: v.calls, distinct: v.distinct.size }])),
    tail,
  };
  // unit 境界ごとの累積 (17 unit 完走区間 = unit 0..17 のうち完走分, 停止 unit = init_count_var)
  const cum = {};
  const seen = new Set();
  let calls_so_far = 0;
  const maxU = Math.max(...Object.keys(perUnit).map(Number), 0);
  const byUnitNew = {};
  for (let k = 0; k < L; k++) {
    const v = mod._sxt_log_at(k); const idx = v >>> 16, unit = v & 0xffff;
    if (!seen.has(idx)) { seen.add(idx); (byUnitNew[unit] ||= []).push(names[idx]); }
  }
  res.trace.new_per_unit = byUnitNew;
  res.trace.events = [];
  for (let k = 0; k < Math.min(L, 20000); k++) { const v = mod._sxt_log_at(k); res.trace.events.push([v & 0xffff, names[v >>> 16]]); }
}
fs.mkdirSync(outDir, { recursive: true });
if (traceFile && mod.FS) {   // guest が書いた JSON Lines を MEMFS から回収 (NULL で fclose して flush してから読む)
  try {
    mod.ccall('shimx_set_trace_file', 'number', ['string'], [null]); fs.writeFileSync(path.join(outDir, tag + '.ftrace.jsonl'), mod.FS.readFile(traceFile)); } catch (e) { res.ftrace_error = String(e && e.message || e); }
}
fs.writeFileSync(path.join(outDir, tag + '.run.json'), JSON.stringify(res, null, 1));
fs.writeFileSync(path.join(outDir, tag + '.stderr.txt'), stderrLines.join('\n') + '\n');
console.log('SXL_RESULT ' + JSON.stringify({ ...res, trace: res.trace ? { ...res.trace, events: undefined, calls: undefined, tail: undefined, per_unit: undefined, new_per_unit: undefined } : undefined, last_stderr: undefined, stack: undefined }));
