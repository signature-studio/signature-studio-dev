// #5741: unit 275 が読む list A (obj=[0x11e4c80]=0x11f7198、list=[obj+188]=0x11f7254) と、
// 0 番地付近 ([0+8]・[0+16]) が unit 0..275 の各 unit の前後で変わるかを記録する。
// 使い方: node trap_triage/probe5741_listA.mjs   (tools/m11 で実行)
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
const hex = (x) => '0x' + BigInt(x).toString(16);
const u64 = (a) => dv().getBigUint64(a, true);
const i32 = (a) => dv().getInt32(a, true) >>> 0;
const LA = 0x11f7254;
const snap = () => [Number(u64(LA)), Number(u64(0 + 8)), Number(u64(0 + 16))].join(',');
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
let prev = snap();
console.log('init listA/[8]/[16]=', prev, 'obj=', hex(i32(0x11e4c80)));
for (let i = 0; i < 276; i++) {
  const r = run(i);
  const cur = snap();
  if (cur !== prev) console.log('unit', i, r, 'changed', prev, '->', cur);
  prev = cur;
}
console.log('final', prev);
