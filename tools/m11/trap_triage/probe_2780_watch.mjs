// #2780 読取りのみの診断 probe: 各 unit 実行の前後で監視番地 (SV_WATCH, 既定 0x10aa1160) の 8B を読み, 値が変わった unit を出す.
// IR・C・survey 本体は変更しない (通常 build で走る). usage: SV_WATCH=0x10aa1160 node probe_2780_watch.mjs <from> <to>
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const W = Number(process.env.SV_WATCH || '0x10aa1160');
const from = +(process.argv[2] || 0), to = +(process.argv[3] || 941);
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
console.log('watch 0x' + W.toString(16) + ' boot ' + hex(prev));
for (let i = from; i <= to; i++) {
  let kind;
  try { kind = mod._m11_call_unit(i) === 1 ? 'ok' : 'nonok'; } catch (e) {
    kind = (e && e.m11_dllmain_done !== undefined) ? 'halt0' : 'exc';
    mod.__emscripten_stack_restore(sp0);
  }
  const cur = rd();
  if (cur[0] !== prev[0] || cur[1] !== prev[1]) console.log(`unit ${i} ${kind} ${hex(prev)} -> ${hex(cur)}`);
  prev = cur;
}
console.log('end ' + hex(prev));
