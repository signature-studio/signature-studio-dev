// #5741: 80e040 (obj = *(*(G)), G=VA 0x15e4c80) と 867510 (list = *(G2)+0xbc, G2=VA 0x15f7198) の
// 間接段数を実値で確かめる。LVA = VA - 0x400000。各 unit の後に G・G2 の段の値を出す。
// 使い方: node trap_triage/probe5741_deref.mjs   (tools/m11 で実行)
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
const sp0 = mod._emscripten_stack_get_current();
const dv = () => new DataView(mod.HEAPU8.buffer);
const hex = (x) => '0x' + Number(x).toString(16);
const u64 = (a) => dv().getBigUint64(a, true);
const G = 0x11e4c80, G2 = 0x11f7198;
const snap = (tag) => {
  const g1 = Number(u64(G));                 // [G]
  const obj = Number(u64(g1));                // [[G]]  (80e040 の obj)
  const g2 = Number(u64(G2));                 // [G2]   (867510 の G2)
  const listB = Number(u64(g2 + 0xbc));        // [G2+188] (867510 の list)
  const listA = Number(u64(obj + 0xbc));       // [obj+188] (80e040 の list)
  console.log(tag, '[G]=' + hex(g1), '[[G]]=' + hex(obj), '[G2]=' + hex(g2), 'listB=' + hex(listB), 'listA=' + hex(listA));
};
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
snap('init');
for (let i = 0; i < 276; i++) {
  if (i === 114 || i === 275) snap('before' + i);
  const r = run(i);
  if (i === 114 || i === 275) { console.log('  unit', i, r); snap('after' + i); }
}
