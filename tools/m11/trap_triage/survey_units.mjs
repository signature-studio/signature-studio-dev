// per-unit survey: 各 unit の結果 (ok/trap 種別/wasm frame 名/stub 呼出) を JSON で出力する (#130)
import fs from 'fs';
Error.stackTraceLimit = 40;
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const errs = [];
// trace 行 (m11_ov.c の M11_TRACE) は診断用の別チャンネル: rec.err には入れない (SV_TRACE_AT の有無で survey JSON を変えないため, #495)
const TRACE_RE = /^\[m11\]\[(icall|icall-miss|InitUnits|unit \d+\/\d+|InitLib|UStrAsg|longjmp)\]/;
const mod = await m2.default({ printErr: (s) => { s = String(s); const tr = TRACE_RE.test(s); if (!tr) errs.push(s); if (tr || process.env.SV_TRACE_AT) fs.writeSync(2, s + '\n'); } });
if (process.env.SV_TRACE_PROBE) mod.m11_trace_probe = 1;   // trace が汚した shadow stack の最深距離を測る (M11_TRACE_SPAN の裏取り)
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1); if (process.env.SV_TRACE) mod._m11_set_trace(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const stubCounts = () => { const o = {}; for (let i = 0; i < mod._m11_stub_uniq(); i++) o[mod.UTF8ToString(mod._m11_stub_name(i))] = mod._m11_stub_count(i); return o; };
const per = [];
const only = process.env.SV_ONLY ? process.env.SV_ONLY.split(',').map(Number) : null;
for (let i = 0; i < 942; i++) {
  if (only && !only.includes(i)) continue;
  if (process.env.SV_TRACE_AT && String(i) === process.env.SV_TRACE_AT) mod._m11_set_trace(1);
  if (process.env.SV_STK_FILL) { const sp = mod._emscripten_stack_get_current(); mod.HEAPU8.fill(parseInt(process.env.SV_STK_FILL, 16), sp - 8192, sp); }   // 各 unit の直前に SP 直下 8 KiB を埋める (残骸への感度の検査)
  const before = stubCounts(); const va0 = Number(mod._m11_va_used());
  const e0 = errs.length;
  if (process.env.SV_PROG) fs.writeSync(2, 'unit ' + i + '\n');
  const rec = { unit: i, va: '0x' + mod._m11_unit_va(i).toString(16) };
  try {
    const r = mod._m11_call_unit(i);
    rec.kind = r === 1 ? 'ok' : r === 0 ? 'noproc' : 'miss';
  } catch (e) {
    if (e && e.m11_dllmain_done !== undefined) { rec.kind = 'halt0'; rec.frames = ((e.stack) || '').split('\n').filter(l => /wasm-function/.test(l)).slice(0, 30).map(l => l.trim()); }
    else {
      const msg = ((e && e.message) || String(e)).split('\n')[0];
      rec.kind = /out of bounds/.test(msg) && !/table/.test(msg) ? 'oob' : /abort/i.test(msg) ? 'abort' : 'other';
      rec.msg = msg;
      rec.frames = ((e && e.stack) || '').split('\n').filter(l => /wasm-function|at /.test(l)).slice(1, 30).map(l => l.trim().replace(/^at /, '').split(' ')[0]);
    }
    mod.__emscripten_stack_restore(sp0);
  }
  const after = stubCounts(); rec.va_mb = +((Number(mod._m11_va_used()) - va0) / 1e6).toFixed(1); if (!rec.va_mb) delete rec.va_mb;
  const d = {}; for (const k in after) if (after[k] !== (before[k] || 0)) d[k] = after[k] - (before[k] || 0);
  if (Object.keys(d).length) rec.stubs = d;
  if (errs.length > e0) rec.err = errs.slice(e0).slice(0, 3);
  per.push(rec);
}
fs.writeFileSync(process.argv[2] || '/dev/stdout', JSON.stringify(per, null, 1));
const kinds = {}; for (const r of per) kinds[r.kind] = (kinds[r.kind] || 0) + 1;
console.log('SURVEY_UNITS ' + JSON.stringify(kinds));
if (process.env.SV_TRACE_PROBE) console.log('TRACE_MAXDIRTY ' + (mod.m11_maxdirty | 0));
