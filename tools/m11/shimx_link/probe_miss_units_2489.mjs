// unit 1..idx を順に実行し、各 unit の後の icall-miss の累計 (総数・一意 target) を出す。どの unit で miss が増えたかを見る (SHX-T9h #2489)。
//   node probe_miss_units_2489.mjs <m11_sx_*.cjs | m11_boot.cjs 絶対パス> [unit_index 既定 22]
//   素材: tools/m11/work/ (work-m11 と再生成した work/m11_image.bin)
import fs from 'fs';
import path from 'path';

const M11 = path.resolve(new URL('../', import.meta.url).pathname);
const cjs = path.resolve(process.argv[2]);
const idx = Number(process.argv[3] ?? 22);
const m2 = await import(cjs);
const image = fs.readFileSync(M11 + '/work/m11_image.bin');
const errs = [];
const mod = await (m2.default || m2)({ printErr: (s) => { errs.push(String(s)); } });
mod.HEAPU8.set(image, 0);
mod._m11_set_survey(1);
const sp = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) throw e; mod.__emscripten_stack_restore(sp); }
const sp0 = mod._emscripten_stack_get_current();
let prev = '';
for (let i = 0; i < idx; i++) {
  try { mod._m11_call_unit(i); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) { try { mod.__emscripten_stack_restore(sp0); } catch (_) {} } }
  const uniq = []; for (let k = 0; k < mod._m11_icall_miss_uniq(); k++) uniq.push(mod._m11_icall_miss_at(k).toString(16));
  const cur = 'total=' + mod._m11_icall_miss() + ' uniq=' + uniq.join(',');
  if (cur !== prev) console.log('MISS_AFTER|unit', i + 1, cur);
  prev = cur;
}
console.log('MISS_FINAL|', prev);
for (const l of errs.slice(0, 0)) console.log(l);
