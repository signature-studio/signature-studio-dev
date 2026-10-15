// watch_slot_942.mjs: watch_ir_942.py で観測フックを入れた stage4 (S4_NAME) を通常 boot (run_stage4.mjs と同じ経路) で動かし、
// 各フックの時点で指定アドレス 8B の値を読んだリング (固定アドレス 0x11FFF000) を出す (#942 受入 2・診断専用)。
// 使い方: S4_NAME=watch942 S4_IMAGE=tools/m11/work/m11_image.bin WATCH_ADDR=0x10aa10b8 node tools/m11/ldfix/watch_slot_942.mjs
// 注意: S4_NAME の build は WATCH_ADDR と同じ値で watch_ir_942.py により作る (IR 内のアドレスは定数)。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const W = S4 + '/work/stage4/' + (process.env.S4_NAME || 'watch942') + '/';
const RING = 0x11FFF000;
const m2 = await import(W + 'm11_boot.cjs');
const mod = await (m2.default ? m2.default({ printErr: () => {} }) : m2());
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (W + 'm11_image.bin')), 0);
let threw = null;
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) threw = (e && e.message) || String(e);
}
const dv = new DataView(mod.HEAPU8.buffer, mod.HEAPU8.byteOffset, mod.HEAPU8.byteLength);
const n = dv.getUint32(RING, true);
const rows = [];
for (let k = 0; k < Math.min(n, 2000); k++) {
  const o = RING + 0x10 + 16 * k;
  rows.push({ id: Number(dv.getBigUint64(o, true)), value: dv.getBigUint64(o + 8, true) });
}
const addr = Number(process.env.WATCH_ADDR || '0x10aa10b8');
const final = dv.getBigUint64(addr, true);
console.log('WATCH ' + JSON.stringify({ addr: '0x' + addr.toString(16), hooks: n, threw, final: '0x' + final.toString(16) }));
let prev = null;
rows.forEach((r, k) => {
  const changed = prev !== null && r.value !== prev;
  if (changed || k >= rows.length - 4 || process.env.WATCH_ALL) console.log(`WATCH_ROW ${k} id=${r.id}${changed ? ' *' : ''} value=0x${r.value.toString(16)}`);
  prev = r.value;
});
