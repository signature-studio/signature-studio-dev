// #881: unit 275 直前で 80e040 のループが読む要素 (list=[obj+188]=0 のとき 50aa70 は [0+8] を基底, [0+16] を件数として読む)
// を走査し, 最初に 864fe0 の [this+8] が線形メモリ外になる添字と値を表示する。
// 使い方: node trap_triage/probe881_275b.mjs
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const G = 0x11e4c80;
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
const hex = (x) => '0x' + BigInt(x).toString(16);
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
for (let i = 0; i < 275; i++) run(i);
const memLen = mod.HEAPU8.length;
const base = Number(u64(8)), cnt = Number(u64(16) & 0xffffffffn);
console.log('list=0 の読み: [0+8]=base', hex(base), '[0+16]=count', cnt, 'linear mem', hex(memLen));
let shown = 0;
for (let k = 0; k < cnt && shown < 5; k++) {
  const p = Number(u64(base + 8 * k));
  const inRange = p + 8 <= memLen;
  if (!inRange || k < 2) { console.log('  idx', k, 'this=', hex(p), 'this+8 in range:', inRange); shown++; }
  if (!inRange) break;
}
console.log('unit 275 result', run(275));
