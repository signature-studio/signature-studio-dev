// #1676: list B (G2=i32[0x11f7198], list=[G2+188]) のヘッダ +8 (base) が何によって 0 のまま
// 生成・変更されるかを、unit ごとに監視する。base が 0 から変わった unit と、
// base 0 のまま list B に push (cnt 増加) した unit を出す。
// 使い方: node trap_triage/probe1676_listB_writes.mjs
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
const u64 = (a) => dv().getBigUint64(a, true);
const i32 = (a) => dv().getInt32(a, true) >>> 0;
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
const state = () => {
  const B = i32(0x11f7198);
  const L = Number(u64(B + 188));
  if (!L) return { B, L: 0, base: null, cnt: null };
  return { B, L, base: u64(L + 8), cnt: u64(L + 16) };
};
let prev = state();
const hex = (x) => (x === null ? 'null' : '0x' + BigInt(x).toString(16));
console.log('init', 'B', hex(prev.B), 'L', hex(prev.L), 'base', hex(prev.base), 'cnt', String(prev.cnt));
for (let i = 0; i < 942; i++) {
  const r = run(i);
  const s = state();
  const changed = s.L !== prev.L || s.base !== prev.base || s.cnt !== prev.cnt;
  if (changed) {
    console.log('unit', i, r, 'L', hex(s.L), 'base', hex(s.base), 'cnt', String(s.cnt), '(prev base', hex(prev.base), 'cnt', String(prev.cnt) + ')');
  }
  prev = s;
}
console.log('final', 'B', hex(prev.B), 'L', hex(prev.L), 'base', hex(prev.base), 'cnt', String(prev.cnt));
