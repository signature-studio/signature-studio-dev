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
const res = [];
for (let i = 0; i < 942; i++) res.push(mod._m11_unit_va(i).toString(16));
fs.writeFileSync(out, res.join('\n') + '\n');
console.log('units', res.length, 'nonzero', res.filter(x => x !== '0').length);
