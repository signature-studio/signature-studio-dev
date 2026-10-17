// trap114_src_read_5280.mjs: trap114_src_5280.py の変種 (stage4 ビルド済み) を survey と同じ呼び出しで走らせ、
// trap した unit ごとに call site B の直前 memcpy の源 (%53) と、その 0 番目・1 番目・6 番目 qword を出す (#5280 受入 1 の残り・診断用)。
// 使い方: S4_NAME=t114src S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap114_src_read_5280.mjs
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 't114src');
const BASE = 0x11FF8300;
const SLOT = { cnt: 0, src: 8, p0: 16, p6: 24, p1: 32 };
const SPAN = 40;
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const hx = (v) => '0x' + BigInt.asUintN(64, v).toString(16);
const clr = () => mod.HEAPU8.fill(0, BASE, BASE + SPAN);
const read = () => {
  const dv = new DataView(mod.HEAPU8.buffer);
  const u = (k) => dv.getBigUint64(BASE + SLOT[k], true);
  return { memcpy_hits: Number(u('cnt')), src: hx(u('src')), qword0: hx(u('p0')), qword1: hx(u('p1')), qword6_to_18787504: hx(u('p6')) };
};
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
clr();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const out = [];
for (let i = 0; i < 942; i++) {
  clr();
  let kind = 'ok';
  try { mod._m11_call_unit(i); } catch (e) {
    const halt = !!(e && e.m11_dllmain_done !== undefined);
    kind = halt ? 'halt0->longjmp' : ((e && e.message) || String(e)).split('\n')[0];
    mod.__emscripten_stack_restore(sp0);
  }
  const r = read();
  if (kind !== 'ok' || r.memcpy_hits > 0) out.push({ i, va: hx(BigInt(mod._m11_unit_va(i))), kind, ...r });
}
console.log('TRAP114_SRC ' + JSON.stringify({ units: out }));
