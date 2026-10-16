// #5715 (CI-238): 全 942 unit を survey と同じ手順で実行し、unit ごとに function_439f90 の入口計数を記録する (計測専用).
// 出力: argv[2] (json) = [{unit, kind, reached: 0|1}]. probe は m11_439f90_probe_rt.c の m11_fe_439f90 (_m11_fe_439f90_get / _clear)。
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
if (typeof mod._m11_fe_get !== 'function') { console.log('REACH_439F90 ERROR: probe export 無し'); process.exit(1); }
const per = [];
for (let i = 0; i < 942; i++) {
  if (only && !only.includes(i)) continue;
  mod._m11_fe_clear();
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
  rec.reached = mod._m11_fe_get(0);
  rec.control_417b70 = mod._m11_fe_get(1);
  per.push(rec);
}
fs.writeFileSync(process.argv[2] || '/dev/stdout', JSON.stringify(per));
const kinds = {}; for (const r of per) kinds[r.kind] = (kinds[r.kind] || 0) + 1;
const reached = per.filter(r => r.reached === 1).length;
const ctl = per.filter(r => r.control_417b70 === 1).length;
console.log('REACH_439F90 units=' + per.length + ' reached=' + reached + ' not_reached=' + (per.length - reached) + ' control_417b70_reached=' + ctl + ' kinds=' + JSON.stringify(kinds));
