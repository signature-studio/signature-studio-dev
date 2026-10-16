// watch_survey_5533.mjs: watch_ir_5533.py のフックを入れた stage4 (S4_NAME) を survey と同じ経路 (set_survey → boot → 各 unit) で動かし、
// unit ごとに値のリング (固定アドレス 0x11FFF000) を読む (#5533 受入 1・診断専用)。
// 使い方: S4_NAME=watch5533 node tools/m11/ldfix/watch_survey_5533.mjs > out.txt
// 注意: 各 unit の前に ring を 0 に戻す。ring の id は 1=X の段1, 2=X, 3=P, 4=P の指す 4B の値 (watch_ir_5533.py 参照)。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/..';
const W = S4 + '/work/stage4/' + (process.env.S4_NAME || 'watch5533') + '/';
const RING = 0x11FFF000;
const m2 = await import(W + 'm11_boot.cjs');
const mod = await (m2.default ? m2.default({ printErr: () => {} }) : m2());
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/work/m11_image.bin')), 0);
const dv = () => new DataView(mod.HEAPU8.buffer, mod.HEAPU8.byteOffset, mod.HEAPU8.byteLength);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
let bootThrew = null, done = false;
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) { done = true; mod.__emscripten_stack_restore(sp_boot); }
  else bootThrew = (e && e.message) || String(e);
}
const sp0 = mod._emscripten_stack_get_current();
const only = process.env.WATCH_UNITS ? process.env.WATCH_UNITS.split(',').map(Number) : null;
let hitUnits = 0;
for (let i = 0; i < 942; i++) {
  if (only && !only.includes(i)) continue;
  dv().setUint32(RING, 0, true);
  let r = null, err = null;
  try { r = mod._m11_call_unit(i); } catch (e) {
    err = (e && e.m11_dllmain_done !== undefined) ? 'halt0' : (((e && e.message) || String(e)).split('\n')[0]);
    mod.__emscripten_stack_restore(sp0);
  }
  const n = dv().getUint32(RING, true);
  if (n > 0) {
    hitUnits++;
    const rows = [];
    for (let k = 0; k < Math.min(n, 2000); k++) {
      const o = RING + 0x10 + 16 * k;
      rows.push([Number(dv().getBigUint64(o, true)), '0x' + dv().getBigUint64(o + 8, true).toString(16)]);
    }
    console.log('WATCH_UNIT ' + JSON.stringify({ i, va: '0x' + mod._m11_unit_va(i).toString(16), ret: r, err, hooks: n, rows: rows.slice(0, 64) }));
  }
}
console.log('WATCH_DONE ' + JSON.stringify({ dllmain_done: done, boot_threw: bootThrew, units_with_hooks: hitUnits }));
