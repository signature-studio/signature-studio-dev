// run_dest_2203.mjs (#2203): watch_2118.sh の run_2118.mjs と同じ実行経路 (boot → m11_call_unit) で、
// [d413060] と [r2118] (j=12 の 412c20 前後の 2 区間指紋) と unit 結果を出す。読取りの計装だけ・書込みは無し。
//   usage: M11_DIR=<tools/m11> OUT_LOG=<file> node run_dest_2203.mjs 0,1,158
import fs from 'fs';
const M11 = process.env.M11_DIR;
const units = process.argv[2].split(',').map(Number);
const m2 = await import(M11 + '/work/m11_boot.cjs');
const lines = [];
const mod = await m2.default({ printErr: (s) => { lines.push(String(s)); } });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
for (const u of units) {
  lines.push('unit ' + u);
  try { const r = mod._m11_call_unit(u); lines.push('RES ' + u + ' ' + (r === 1 ? 'ok' : r === 0 ? 'noproc' : 'miss:' + r)); }
  catch (e) { mod.__emscripten_stack_restore(sp0); lines.push('RES ' + u + ' trap:' + String((e && e.message) || e).split('\n')[0]); }
}
fs.writeFileSync(process.env.OUT_LOG, lines.filter((s) => /^(\[d413060\]|\[r2118\]|unit |RES )/.test(s)).join('\n') + '\n');
