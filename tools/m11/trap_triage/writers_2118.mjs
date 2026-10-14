// #2118 (M11-N139): 計装 build (watch_range_2118.c・M11_KEEP_BOOT_O=1) で、先行 unit (既定 0,1) を実行し、
// 2 区間への書込み (stderr の [rw] 行) を site 単位で出す。書込みの IR 行は sites.json で引く。
//   usage: node writers_2118.mjs <units csv> <sites.json> <out.log>
// stderr は printErr で受け、[rw] 行だけを out.log に残す (他は捨てる)。
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const [unitsArg, sitesPath, outPath] = process.argv.slice(2);
const units = unitsArg.split(',').filter(Boolean).map(Number);
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
const res = [];
for (const u of units) {
  lines.push('unit ' + u);
  try { res.push(u + ':' + mod._m11_call_unit(u)); } catch (e) {
    mod.__emscripten_stack_restore(sp0);
    res.push(u + ':trap');
  }
}
const rw = lines.filter((s) => s.startsWith('[rw]') || s.startsWith('unit '));
fs.writeFileSync(outPath, rw.join('\n') + '\n');
console.log('results', res.join(' '), 'rw_lines', rw.filter((s) => s.startsWith('[rw]')).length);
