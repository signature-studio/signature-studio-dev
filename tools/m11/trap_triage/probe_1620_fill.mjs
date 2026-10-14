// #1620 診断 (読取り + stack 埋め。IR 不変): 各 unit の前に、現在 SP より下の stack 領域を FILL で埋める。
// 0x10a9f910 の遷移と unit ごとの戻り値が、埋め値に依存するかを見る。usage: node fill_probe.mjs <fillByte> <from> <to>
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const W = 0x10a9f910;
const fill = +(process.argv[2] ?? 0), from = +(process.argv[3] || 0), to = +(process.argv[4] || 941);
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
const rd = () => { const dv = new DataView(mod.HEAPU8.buffer); return [dv.getUint32(W, true), dv.getUint32(W + 4, true)]; };
const hex = (v) => '0x' + (v[1] ? v[1].toString(16) + '_' : '') + v[0].toString(16);
let prev = rd();
const out = [];
for (let i = from; i <= to; i++) {
  const sp = mod._emscripten_stack_get_current();
  if (fill >= 0) mod.HEAPU8.fill(fill, sp - 65536, sp);
  let kind;
  try { kind = mod._m11_call_unit(i) === 1 ? 'ok' : 'nonok'; } catch (e) {
    kind = (e && e.m11_dllmain_done !== undefined) ? 'halt0' : 'exc';
    mod.__emscripten_stack_restore(sp0);
  }
  const cur = rd();
  if (cur[0] !== prev[0] || cur[1] !== prev[1]) out.push(`unit ${i} ${kind} ${hex(prev)} -> ${hex(cur)}`);
  prev = cur;
}
console.log('fill=' + fill + ' end ' + hex(prev));
console.log(out.join('\n'));
