// watch_survey_5533.mjs: watch_ir_5533.py のフックを入れた stage4 (S4_NAME) を survey と同じ経路 (set_survey → boot → 各 unit) で動かし、
// unit ごとに値の配列 (globalThis.__m11_wv・watch_shim_5533.c が積む) を読む (#5533 受入 1・診断専用)。
// 使い方: S4_NAME=watch5533 node tools/m11/ldfix/watch_survey_5533.mjs > out.txt
// 注意: 各 unit の前に配列を空にする。id は 0=入口, 1=%359, 2=X (%363), 3=P (%491), 4=P の指す 4B (watch_ir_5533.py 参照)。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/..';
const W = S4 + '/work/stage4/' + (process.env.S4_NAME || 'watch5533') + '/';
const m2 = await import(W + 'm11_boot.cjs');
const mod = await (m2.default ? m2.default({ printErr: () => {} }) : m2());
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/work/m11_image.bin')), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
let bootThrew = null, done = false;
globalThis.__m11_wv = [];
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) { done = true; mod.__emscripten_stack_restore(sp_boot); }
  else bootThrew = (e && e.message) || String(e);
}
const bootHooks = (globalThis.__m11_wv || []).length;
const sp0 = mod._emscripten_stack_get_current();
const only = process.env.WATCH_UNITS ? process.env.WATCH_UNITS.split(',').map(Number) : null;
let hitUnits = 0;
for (let i = 0; i < 942; i++) {
  if (only && !only.includes(i)) continue;
  globalThis.__m11_wv = [];
  let r = null, err = null;
  try { r = mod._m11_call_unit(i); } catch (e) {
    err = (e && e.m11_dllmain_done !== undefined) ? 'halt0' : (((e && e.message) || String(e)).split('\n')[0]);
    mod.__emscripten_stack_restore(sp0);
  }
  const rows = globalThis.__m11_wv || [];
  if (rows.length > 0) {
    hitUnits++;
    console.log('WATCH_UNIT ' + JSON.stringify({ i, va: '0x' + mod._m11_unit_va(i).toString(16), ret: r, err, hooks: rows.length,
      rows: rows.slice(0, 64).map(([id, v]) => [Number(id), '0x' + BigInt(v).toString(16)]) }));
  }
}
console.log('WATCH_DONE ' + JSON.stringify({ dllmain_done: done, boot_threw: bootThrew, boot_hooks: bootHooks, units_with_hooks: hitUnits }));
