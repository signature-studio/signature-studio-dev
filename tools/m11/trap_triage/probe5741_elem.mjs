// #5741: unit 275 直前の list (= [[G]]+188) の base(+8)・count(+16) と、80e040 の添字ごとの this を読む。
// 50aa70(list, idx): base=[list+8], count=[list+16], 要素は [base+8*idx]。OOB になる this の添字を特定する。
// 使い方: node trap_triage/probe5741_elem.mjs   (tools/m11 で実行)
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
const G = 0x11e4c80;
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
for (let i = 0; i < 275; i++) run(i);
const obj = Number(u64(Number(u64(G))));
const list = Number(u64(obj + 0xbc));
const base = Number(u64(list + 8));
const cnt = Number(u64(list + 16));
console.log('count via 8657d0 (eax)=', cnt, '; loop idx 0..', cnt-1);
console.log('before275 obj=' + hex(obj) + ' list=' + hex(list) + ' base=' + hex(base) + ' count=' + cnt);
for (let k = 0; k < 4; k++) console.log('  mem[' + hex(8 * k) + ']=' + hex(u64(8 * k)));
const LIN=mod.HEAPU8.length; for (let idx = 0; idx < 16; idx++) { const t=Number(u64(base + 8*idx)); const inr = t>=0 && t+8+8<=LIN; console.log('  idx', idx, 'this=', hex(t), 'this+8 in linear mem:', inr, 'mem size', hex(LIN)); }
console.log('unit 275 ->', run(275));
