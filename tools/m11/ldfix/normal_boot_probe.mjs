// normal_boot_probe.mjs: 通常 boot (InitUnits あり・survey 無し) の trap 位置と FastMM 状態を取る (#942 受入 1・2)。
// survey (trap_bins.mjs / trap_units.mjs) は InitUnits を抑止するため FastMM 初期化 (function_41ce10) が走らない。
// 使い方: S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/normal_boot_probe.mjs
// 出力: 例外スタック (wasm-function 番号とオフセット)・once-init counter・サイズ→bin 表・bin 表 (k<=172, 4 刻み)・span 表
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 'base');
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const d = new DataView(mod.HEAPU8.buffer);
const MEM = BigInt(mod.HEAPU8.length);
const hx = (n) => '0x' + BigInt(n).toString(16);
try { mod._m11_boot_enter(0n, 1n); console.log('boot returned'); } catch (e) {
  console.log('boot threw: ' + e.message);
  console.log(String(e.stack).split('\n').slice(1, 6).join('\n'));
}
console.log('once-init counter(0x11e6a38)=' + d.getInt32(0x11e6a38, true) + ' init_count=' + mod._m11_init_count());
const T = 0x11e6a3c; const sz = new Map();
for (let j = 0; j < 326; j++) sz.set(mod.HEAPU8[T + j], (sz.get(mod.HEAPU8[T + j]) || 0) + 1);
console.log('size->bin table: distinct=' + sz.size + ' max=' + Math.max(...sz.keys()) + ' (entries >=184: ' + [...sz].filter(([k]) => k >= 184).length + ')');
const BASE = 16404744;
let self = 0, live = []; 
for (let k = 0; k <= 172; k += 4) {
  const rbx = BASE + 16 * k; const P = d.getBigUint64(rbx + 8, true);
  if (P === BigInt(rbx)) self++; else live.push(`k${k} P=${hx(P)} F=${P >= 8n && P + 32n < MEM ? hx(d.getBigUint64(Number(P) + 24, true)) : '-'}`);
}
console.log('bins k<=172 (4-stride): self-loop(empty)=' + self + ' non-self=' + live.length);
console.log(live.join('\n'));
for (let idx = 0; idx < 1024; idx++) {
  const s = 18771008 + 16 * idx; const pv = d.getUint32(s + 8, true);
  if (pv !== s) console.log('span list idx ' + idx + ' sentinel=' + hx(s) + ' head=' + hx(pv) + ' [head-8]=' + hx(d.getBigUint64(pv - 8, true)));
}
