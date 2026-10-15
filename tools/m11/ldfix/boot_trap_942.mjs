// boot_trap_942.mjs: 通常 boot (m11_boot_enter) が threw したときの wasm frame chain を出す (#942 受入 2・診断用)。
// 使い方: S4_NAME=prod942 S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/boot_trap_942.mjs
// 出力: BOOT_TRAP {"threw": ..., "units_run": n, "chain": [[wasm 関数 index, offset], ...]}。IR 名は tools/m11/m11_wasmnames.py で引く。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 'fix');
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
mod._m11_set_survey(0);
let threw = null, chain = [];
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) threw = null;
  else {
    threw = ((e && e.message) || String(e)).split('\n')[0];
    chain = e && e.stack ? [...String(e.stack).matchAll(/wasm-function\[(\d+)\]:(0x[0-9a-f]+)/g)].slice(0, 12).map(c => [+c[1], c[2]]) : [];
  }
}
console.log('BOOT_TRAP ' + JSON.stringify({ threw, chain }));
