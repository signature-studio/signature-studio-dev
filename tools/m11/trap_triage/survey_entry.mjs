// #1894: survey_units.mjs と同じ手順で全 unit を実行し, unit ごとに entry probe (m11_entry_probe_rt.c) の到達フラグを記録する.
// probe は M11_ENTRY_PROBE=1 の build でだけ export される (_m11_fe_get / _m11_fe_clear). 既存の survey_units.mjs は変えない.
// 出力: argv[2] (json) = [{unit, kind, fe: [7 個の 0/1]}]. 並びは m11_entry_probe_rt.c の index (0..6) と同じ.
import fs from 'fs';
Error.stackTraceLimit = 40;
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const errs = [];
const TRACE_RE = /^\[m11\]\[(icall|icall-miss|InitUnits|unit \d+\/\d+|InitLib|UStrAsg|longjmp)\]/;
const mod = await m2.default({ printErr: (s) => { s = String(s); if (!TRACE_RE.test(s)) errs.push(s); } });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const only = process.env.SV_ONLY ? process.env.SV_ONLY.split(',').map(Number) : null;
const hasFe = typeof mod._m11_fe_get === 'function';
const fe = () => { if (!hasFe) return null; const a = []; for (let i = 0; i < 8; i++) a.push(mod._m11_fe_get(i)); return a; };
const per = [];
for (let i = 0; i < 942; i++) {
  if (only && !only.includes(i)) continue;
  if (hasFe) mod._m11_fe_clear();
  const rec = { unit: i };
  try {
    const r = mod._m11_call_unit(i);
    rec.kind = r === 1 ? 'ok' : r === 0 ? 'noproc' : 'miss';
  } catch (e) {
    if (e && e.m11_dllmain_done !== undefined) rec.kind = 'halt0';
    else {
      const msg = ((e && e.message) || String(e)).split('\n')[0];
      rec.kind = /out of bounds/.test(msg) && !/table/.test(msg) ? 'oob' : /abort/i.test(msg) ? 'abort' : 'other';
    }
    mod.__emscripten_stack_restore(sp0);
  }
  rec.fe = fe();
  per.push(rec);
}
fs.writeFileSync(process.argv[2] || '/dev/stdout', JSON.stringify(per));
const kinds = {}; for (const r of per) kinds[r.kind] = (kinds[r.kind] || 0) + 1;
console.log('SURVEY_ENTRY ' + JSON.stringify(kinds));
