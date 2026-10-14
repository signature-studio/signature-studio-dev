// per-unit survey: 各 unit の結果 (ok/trap 種別/wasm frame 名/stub 呼出/間接 call hit) を JSON で出力する (#130, #494)
import fs from 'fs';
Error.stackTraceLimit = 40;
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
// frames は wasm 関数 index のままだとビルド間で名前がずれるため, 実行した wasm の export 名で解決して JSON に残す (#483)
const wasmBin = fs.readFileSync(M11 + '/work/m11_boot.cjs.wasm');
const fnNames = new Map();
{
  let pos = 8;
  const leb = () => { let r = 0, s = 0, x; do { x = wasmBin[pos++]; r |= (x & 0x7f) << s; s += 7; } while (x & 0x80); return r >>> 0; };
  while (pos < wasmBin.length) {
    const id = wasmBin[pos++]; const sz = leb(); const end = pos + sz;
    if (id === 7) { const n = leb(); for (let k = 0; k < n; k++) { const l = leb(); const nm = wasmBin.toString('utf8', pos, pos + l); pos += l; const kind = wasmBin[pos++]; const idx = leb(); if (kind === 0 && !fnNames.has(idx)) fnNames.set(idx, nm); } }
    pos = end;
  }
}
const resolve = (f) => { const m = /wasm-function\[(\d+)\]/.exec(f); return m && fnNames.has(+m[1]) ? fnNames.get(+m[1]) : f; };
const errs = [];
// trace 行 (m11_ov.c の M11_TRACE) は診断用の別チャンネル: rec.err には入れない (SV_TRACE_AT の有無で survey JSON を変えないため, #495)
const TRACE_RE = /^\[m11\]\[(icall|icall-miss|InitUnits|unit \d+\/\d+|InitLib|UStrAsg|longjmp)\]/;
// SV_ERR_LOG=<file>: 非 trace の stderr を unit 番号付きで全行 <file> に追記する (rec.err は unit あたり 3 行で切られるため). 既定 OFF
let curUnit = -1;
const errLog = process.env.SV_ERR_LOG ? fs.openSync(process.env.SV_ERR_LOG, 'w') : null;
const mod = await m2.default({ printErr: (s) => { s = String(s); const tr = TRACE_RE.test(s); if (!tr) { errs.push(s); if (errLog !== null) fs.writeSync(errLog, `unit ${curUnit} ${s}\n`); } if (tr || process.env.SV_TRACE_AT) fs.writeSync(2, s + '\n'); } });
if (process.env.SV_TRACE_PROBE) mod.m11_trace_probe = 1;   // trace が汚した shadow stack の最深距離を測る (M11_TRACE_SPAN の裏取り)
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1); if (process.env.SV_TRACE) mod._m11_set_trace(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const stubCounts = () => { const o = {}; for (let i = 0; i < mod._m11_stub_uniq(); i++) o[mod.UTF8ToString(mod._m11_stub_name(i))] = mod._m11_stub_count(i); return o; };
// 間接 call の入口計測 (#494): site = 元バイナリの call 命令 VA / target = 解決先 VA. 値は [ok, miss]. site 1 = 外部 TU からの m11_icall ('ext')
const icallCounts = () => {
  const o = { sites: {}, targets: {} };
  for (const [t, k] of [[0, 'sites'], [1, 'targets']])
    for (let i = 0; i < mod._m11_icall_cnt_n(t); i++) o[k][mod._m11_icall_cnt_key(t, i) >>> 0] = [mod._m11_icall_cnt_ok(t, i), mod._m11_icall_cnt_miss(t, i)];
  return o;
};
const icallName = (k, kind) => kind === 'sites' && k === 1 ? 'ext' : '0x' + k.toString(16);
const icallNamed = (c) => { const o = {}; for (const kind in c) { const e = Object.entries(c[kind]).sort((a, b) => a[0] - b[0]); if (e.length) o[kind] = Object.fromEntries(e.map(([k, v]) => [icallName(+k, kind), v])); } return o; };
const icallDelta = (a, b) => {
  const d = { sites: {}, targets: {} };
  for (const kind in b) for (const k in b[kind]) {
    const p = a[kind][k] || [0, 0]; const v = [b[kind][k][0] - p[0], b[kind][k][1] - p[1]];
    if (v[0] || v[1]) d[kind][k] = v;
  }
  return d;
};
const icall_boot = icallCounts();
// SV_SLOT=<wasm 番地>: 各 unit の前後で 4B の値を読み、変わった unit だけ rec.slot = [前, 後] を付ける (#1869). 計装なしで書込み unit を特定する用
const slotAt = process.env.SV_SLOT ? Number(process.env.SV_SLOT) : null;
const slotVal = () => { const h = mod.HEAPU8; return (h[slotAt] | h[slotAt + 1] << 8 | h[slotAt + 2] << 16 | h[slotAt + 3] << 24) >>> 0; };
if (slotAt !== null) console.log('SLOT_BOOT 0x' + slotAt.toString(16) + ' ' + '0x' + slotVal().toString(16));
const per = [];
const only = process.env.SV_ONLY ? process.env.SV_ONLY.split(',').map(Number) : null;
const skip = process.env.SV_SKIP ? process.env.SV_SKIP.split(',').map(Number) : [];
for (let i = 0; i < 942; i++) {
  if (only && !only.includes(i)) continue;
  if (skip.includes(i)) { per.push({ unit: i, va: '0x' + mod._m11_unit_va(i).toString(16), kind: 'hang' }); continue; }
  if (process.env.SV_TRACE_AT && String(i) === process.env.SV_TRACE_AT) mod._m11_set_trace(1);
  if (process.env.SV_STK_FILL) { const sp = mod._emscripten_stack_get_current(); mod.HEAPU8.fill(parseInt(process.env.SV_STK_FILL, 16), sp - 8192, sp); }   // 各 unit の直前に SP 直下 8 KiB を埋める (残骸への感度の検査)
  const before = stubCounts(); const va0 = Number(mod._m11_va_used());
  const miss0 = mod._m11_icall_miss(), uniq0 = mod._m11_icall_miss_uniq();
  const ic0 = icallCounts();
  const slot0 = slotAt !== null ? slotVal() : 0;
  const e0 = errs.length;
  curUnit = i;
  if (process.env.SV_PROG) fs.writeSync(2, 'unit ' + i + '\n');
  const rec = { unit: i, va: '0x' + mod._m11_unit_va(i).toString(16) };
  try {
    const r = mod._m11_call_unit(i);
    rec.kind = r === 1 ? 'ok' : r === 0 ? 'noproc' : 'miss';
  } catch (e) {
    if (e && e.m11_dllmain_done !== undefined) { rec.kind = 'halt0'; rec.frames = ((e.stack) || '').split('\n').filter(l => /wasm-function/.test(l)).slice(0, 30).map(l => resolve(l.trim())); }
    else {
      const msg = ((e && e.message) || String(e)).split('\n')[0];
      rec.kind = /out of bounds/.test(msg) && !/table/.test(msg) ? 'oob' : /abort/i.test(msg) ? 'abort' : 'other';
      rec.msg = msg;
      rec.frames = ((e && e.stack) || '').split('\n').filter(l => /^\s*at /.test(l)).slice(0, 30).map(l => resolve(l.trim().replace(/^at /, '').split(' ')[0]));   // #663/#684: 旧 slice(1) は先頭行 (trap 直後の wasm frame) を落としていた
      if (process.env.SV_RAW) rec.raw = ((e && e.stack) || '').split('\n').filter(l => /wasm-function/.test(l)).slice(0, 8).map(l => l.trim());   // #684: wasm バイトオフセット付きの生 frame (命令位置の特定用)
    }
    mod.__emscripten_stack_restore(sp0);
  }
  const dm = mod._m11_icall_miss() - miss0;
  if (dm) { rec.miss_n = dm; rec.miss_new = []; for (let k = uniq0; k < mod._m11_icall_miss_uniq(); k++) rec.miss_new.push('0x' + (mod._m11_icall_miss_at(k) >>> 0).toString(16)); }
  const after = stubCounts(); rec.va_mb = +((Number(mod._m11_va_used()) - va0) / 1e6).toFixed(1); if (!rec.va_mb) delete rec.va_mb;
  const d = {}; for (const k in after) if (after[k] !== (before[k] || 0)) d[k] = after[k] - (before[k] || 0);
  if (Object.keys(d).length) rec.stubs = d;
  const ic = icallNamed(icallDelta(ic0, icallCounts())); if (Object.keys(ic).length) rec.icall = ic;
  if (slotAt !== null && slotVal() !== slot0) rec.slot = ['0x' + slot0.toString(16), '0x' + slotVal().toString(16)];
  if (errs.length > e0) rec.err = errs.slice(e0).slice(0, 3);
  per.push(rec);
}
fs.writeFileSync(process.argv[2] || '/dev/stdout', JSON.stringify(per, null, 1));
// 側ファイル <out>.icall.json: boot 段階 (unit 実行前) の hit と全体の累計 (per-unit 配列には boot 分が入らないため)
if (process.argv[2] && !process.argv[2].startsWith('/dev/'))
  fs.writeFileSync(process.argv[2].replace(/\.json$/, '') + '.icall.json', JSON.stringify({ boot: icallNamed(icall_boot), total: icallNamed(icallCounts()), drop: mod._m11_icall_cnt_drop() }, null, 1));
const kinds = {}; for (const r of per) kinds[r.kind] = (kinds[r.kind] || 0) + 1;
console.log('SURVEY_UNITS ' + JSON.stringify(kinds));
if (process.env.SV_TRACE_PROBE) console.log('TRACE_MAXDIRTY ' + (mod.m11_maxdirty | 0));
