// 942 unit を 1 本ずつ隔離実行し (m11_survey.mjs と同じ方式)、unit ごとに shimx 呼出・結果・fail-fast を記録する (CAB-166)。
//   node survey_trace.mjs <m11_sx_trace_*.cjs> [--out DIR]
// shimx の fail-fast (shim_unimplemented → abort) や GUI fail-fast に当たると runtime が死ぬため、
// その場合は新しいインスタンスで boot (survey モード) をやり直して次の unit から続行する (unit 間の状態は引き継がれない)。
// InitTable を壊した unit (clobber) も同様に boot をやり直す (image の書き戻しは shimx の import 状態を壊すため使わない。#773)。
import fs from 'fs';
import path from 'path';

const M11 = path.resolve(new URL('../', import.meta.url).pathname);
const cjs = path.resolve(process.argv[2]);
const outDir = process.argv.includes('--out') ? process.argv[process.argv.indexOf('--out') + 1] : path.dirname(cjs);
const tag = path.basename(cjs).replace(/\.cjs$/, '');
const m2 = await import(cjs);
const image = fs.readFileSync(M11 + '/work/m11_image.bin');
const N = 942;

let errs = [];
async function boot() {
  errs = [];
  const mod = await (m2.default || m2)({ printErr: (s) => { errs.push(String(s)); if (errs.length > 400) errs.shift(); } });
  mod.HEAPU8.set(image, 0);
  mod._m11_set_survey(1);
  if (process.env.SHIMX_TRACE === '1' && mod._shimx_set_trace) mod._shimx_set_trace(1);
  const sp = mod._emscripten_stack_get_current();
  try { mod._m11_boot_enter(0n, 1n); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) throw e; mod.__emscripten_stack_restore(sp); }
  return mod;
}
let mod = await boot();
const HAS = () => typeof mod._sxt_n === 'function';   // 比較用: M11 既存ビルド (sxt 無し) も同じ手順で走査できる
const snap = () => { const n = mod._sxt_n(); const a = new Array(n); for (let i = 0; i < n; i++) a[i] = mod._sxt_count(i); return a; };
const names = () => { if (!HAS()) return []; const n = mod._sxt_n(); const a = []; for (let i = 0; i < n; i++) a.push(mod.UTF8ToString(mod._sxt_name(i))); return a; };
let NAMES = names();
const perUnit = [];
const kinds = {};
const apiUnits = {};
let reboots = 0;
const shimxMsgs = {};   // SHIMX_TRACE=1 で出る [shimx] 行 (GetProcAddress miss / LoadLibrary 失敗 / ...) の集計
let sp0 = mod._emscripten_stack_get_current();
// clobber 検出 (m11_survey.mjs と同じ判定): InitTable (unit 先頭・末尾の proc VA) が boot 直後と同じか。
const unitVa0 = [mod._m11_unit_va(0), mod._m11_unit_va(N - 1)];
const tableIntact = () => mod._m11_unit_va(0) === unitVa0[0] && mod._m11_unit_va(N - 1) === unitVa0[1];
for (let i = 0; i < N; i++) {
  const C0 = HAS() ? snap() : null;
  const e0 = errs.length;
  let kind = 'ok', detail = null;
  const lva = mod._m11_unit_va(i);
  try {
    const r = mod._m11_call_unit(i);
    kind = r === 1 ? 'ok' : r === 0 ? 'noproc' : r === 2 ? 'closure_outside' : 'range';
  } catch (e) {
    if (e && e.m11_dllmain_done !== undefined) kind = 'halt0';
    else {
      const msg = ((e && e.message) || String(e)).split('\n')[0];
      kind = /Aborted|already aborted/.test(msg) ? 'abort' : /out of bounds/.test(msg) ? 'oob' : /unreachable/.test(msg) ? 'unreachable' : 'trap';
      detail = msg;
      if (kind === 'abort') {
        const ff = errs.slice(e0).filter((l) => /FAIL-FAST|fail-fast/.test(l));
        detail = ff.length ? ff[ff.length - 1] : msg;
      }
    }
  }
  let clobbered = false;
  if (!tableIntact()) {
    clobbered = true;
    if (kind !== 'abort') {
      detail = 'InitTable 破壊 (元の kind=' + kind + ')' + (detail ? ': ' + detail : '');
      kind = 'clobber';
    }
  }
  const called = {};
  if (kind !== 'abort' && HAS()) {
    const C1 = snap();
    for (let k = 0; k < C1.length; k++) if (C1[k] !== C0[k]) called[NAMES[k]] = C1[k] - C0[k];
  }
  for (const l of errs.slice(e0)) if (l.startsWith('[shimx]')) { const a = (shimxMsgs[l] ||= { count: 0, first_unit: i + 1 }); a.count++; }
  const msgs = errs.slice(e0).filter((l) => /MessageBox|\[shimx\]/.test(l)).slice(0, 3);
  perUnit.push({ unit: i + 1, lva: '0x' + lva.toString(16), kind, detail, shim_calls: called, ...(clobbered ? { clobbered: true } : {}), ...(msgs.length ? { msgs } : {}) });
  kinds[kind] = (kinds[kind] || 0) + 1;
  for (const [nm, c] of Object.entries(called)) { const a = (apiUnits[nm] ||= { units: 0, calls: 0, first_unit: i + 1 }); a.units++; a.calls += c; }
  if (kind === 'abort' || clobbered) {
    reboots++;
    mod = await boot(); NAMES = names(); sp0 = mod._emscripten_stack_get_current();
  } else if (kind !== 'ok' && kind !== 'noproc' && kind !== 'closure_outside') {
    try { mod.__emscripten_stack_restore(sp0); } catch (_) {}
  }
}
const summary = {
  variant: tag, units: N, kinds, reboots, shimx_trace_msgs: shimxMsgs,
  api_units: Object.fromEntries(Object.entries(apiUnits).sort((a, b) => b[1].units - a[1].units)),
  aborts: perUnit.filter((u) => u.kind === 'abort').map((u) => ({ unit: u.unit, lva: u.lva, detail: u.detail })),
};
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, tag + '.survey.json'), JSON.stringify({ summary, per_unit: perUnit }, null, 1));
console.log('SXL_SURVEY ' + JSON.stringify({ ...summary, api_units: Object.keys(summary.api_units).length, aborts: summary.aborts.length }));
