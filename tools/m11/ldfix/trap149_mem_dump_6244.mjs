// trap149_mem_dump_6244.mjs: unit 149 の trap 時点で 0x10aa13e0..0x10aa1460 を採る (#6244・診断)。
// 使い方: S4_NAME=t149 S4_IMAGE=tools/m11/work/m11_image.bin node trap149_mem_dump_6244.mjs
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 't149');
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const BASE = 0x10aa13e0, LEN = 0x80;
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
for (let i = 0; i < 942; i++) {
  let kind = 'ok';
  try { mod._m11_call_unit(i); } catch (e) {
    kind = (e && e.m11_dllmain_done !== undefined) ? 'halt0' : ((e && e.message) || String(e)).split('\n')[0];
    mod.__emscripten_stack_restore(sp0);
  }
  if (i === 149) {
    const hex = Buffer.from(mod.HEAPU8.slice(BASE, BASE + LEN)).toString('hex');
    console.log('MEM149 ' + JSON.stringify({ kind, base: '0x' + BASE.toString(16), hex }));
    break;
  }
}
