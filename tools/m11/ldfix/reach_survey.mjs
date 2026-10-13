// reach_survey.mjs — #509: fnhit 計装ビルド (reach_509.sh) の m11_probe.cjs で 942 unit を 1 本ずつ実行し、
// 計装した関数 (K = 0..N-1) の入口通過回数を unit ごとに出す。使い方: node reach_survey.mjs PROBE.cjs IMAGE.bin OUT.json
import fs from 'fs';
const [cjs, image, out] = process.argv.slice(2);
const m2 = await import(cjs);
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(image), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const N = mod._m11_fnhit_n();
const per = [];
for (let i = 0; i < 942; i++) {
  mod._m11_fnhit_reset();
  let kind;
  try { const r = mod._m11_call_unit(i); kind = r === 1 ? 'ok' : r === 0 ? 'noproc' : 'miss'; }
  catch (e) {
    if (e && e.m11_dllmain_done !== undefined) kind = 'halt0';
    else { const msg = ((e && e.message) || String(e)).split('\n')[0]; kind = /out of bounds/.test(msg) && !/table/.test(msg) ? 'oob' : /abort/i.test(msg) ? 'abort' : 'other'; }
    mod.__emscripten_stack_restore(sp0);
  }
  const hits = {};
  for (let k = 0; k < N; k++) { const h = mod._m11_fnhit_get(k); if (h) hits[k] = h; }
  per.push({ unit: i, kind, hits });
}
fs.writeFileSync(out, JSON.stringify(per));
console.log('REACH_SURVEY units=' + per.length + ' instrumented=' + N);
