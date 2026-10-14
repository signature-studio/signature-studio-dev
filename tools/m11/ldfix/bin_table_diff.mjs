// bin_table_diff.mjs: bin 表 (BASE + 16*k, k=0..255) の boot 前後の差分と、P の指す先の種別を取る (#942 受入 2・書き込み元の切り分け)。
// 使い方: S4_NAME=base|fix node tools/m11/ldfix/bin_table_diff.mjs
// boot 中に書き込まれた k を列挙する。書き込みが無ければ changed=0。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 'fix');
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (S4 + '/../work/m11_image.bin')), 0);
const BASE = 16404744;
const N = 256;
const LEN = 16 * N;
const MEM = mod.HEAPU8.length;
const snap = () => mod.HEAPU8.slice(BASE, BASE + LEN);
const pre = snap();
const sp_boot = mod._emscripten_stack_get_current();
let boot = 'no trap';
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  boot = e.message;
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const post = snap();
const dv = (buf) => new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
const changed = [];
for (let k = 0; k < N; k++) {
  const o = 16 * k;
  let diff = false;
  for (let i = 0; i < 16; i++) if (pre[o + i] !== post[o + i]) diff = true;
  if (diff) changed.push(k);
}
console.log('boot: ' + boot);
console.log('changed_slots: ' + changed.length + ' ' + JSON.stringify(changed));
const P = (buf, k) => dv(buf).getBigUint64(16 * k + 8, true);
for (const k of [0, 1, 100, 171, 172, 173, 183, 184, 185, 186, 215, 236, 255]) {
  const p = Number(P(pre, k));
  const inMem = p > 0 && p + 32 < MEM;
  const head = inMem ? Array.from(mod.HEAPU8.slice(p, p + 4)).map((x) => x.toString(16).padStart(2, '0')).join(' ') : 'n/a';
  console.log(`k${k} P=0x${p.toString(16)} pre==post=${P(pre, k) === P(post, k)} head_bytes=[${head}]`);
}
