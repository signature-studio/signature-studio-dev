// #5695 補助: 0x12ba808 近傍 (0..0x1000) の非 0 バイト数を unit 実行前後で数える (対象の構造体が実際にこのアドレスにあるかの確認)。
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const base = 0x12ba808, nz = () => { let n = 0; for (let i = 0; i < 0x1000; i++) if (mod.HEAPU8[base + i]) n++; return n; };
console.log('nonzero bytes in [base, base+0x1000) at boot end:', nz());
const sp0 = mod._emscripten_stack_get_current();
for (let i = 0; i < 942; i++) {
  try { mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); }
  if (i === 895 || i === 941) console.log('after unit', i, 'nonzero=', nz());
}
