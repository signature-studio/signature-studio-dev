// trap_units.mjs: survey と同じ呼び出しで unit ごとの trap の最上位 wasm frame を取る (#942 受入 1)。
// 使い方: S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_units.mjs
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 'fix');
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const out = [];
for (let i = 0; i < 942; i++) {
  try { mod._m11_call_unit(i); } catch (e) {
    if (e && e.m11_dllmain_done !== undefined) { out.push({ i, va: mod._m11_unit_va(i), kind: 'halt0', frame: null }); }
    else {
      const m = e && e.stack && /wasm-function\[(\d+)\]/.exec(e.stack);
      const chain = e && e.stack ? [...String(e.stack).matchAll(/wasm-function\[(\d+)\]:(0x[0-9a-f]+)/g)].slice(0, 8).map(c => [+c[1], c[2]]) : [];
      out.push({ i, va: mod._m11_unit_va(i), kind: ((e && e.message) || String(e)).split('\n')[0], frame: m ? +m[1] : null, chain });
    }
    mod.__emscripten_stack_restore(sp0);
  }
}
console.log('TRAP_UNITS ' + JSON.stringify(out.map(o => ({ ...o, va: '0x' + Number(o.va).toString(16) }))));
