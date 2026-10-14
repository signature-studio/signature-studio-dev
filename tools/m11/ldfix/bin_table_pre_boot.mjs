// bin_table_pre_boot.mjs: FastMM bin 表 (BASE + 16*k) の状態を boot 前 (イメージ読込直後) と boot 後で取る (#942 受入 2)。
// 使い方: S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/bin_table_pre_boot.mjs
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 'fix');
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const MEM = BigInt(mod.HEAPU8.length);
const BASE = 16404744;
const d = new DataView(mod.HEAPU8.buffer);
const scan = (tag) => {
  const out = [];
  for (let k = 0; k < 256; k++) {
    const P = d.getBigUint64(BASE + 16 * k + 8, true);
    if (P < 8n || P + 32n >= MEM) continue;
    const F = d.getBigUint64(Number(P) + 24, true);
    const bad = F !== 0n && (F < 8n || F >= MEM);
    out.push(`k${k} P=0x${P.toString(16)} F=0x${F.toString(16)}${bad ? ' OOB' : ''}`);
  }
  console.log(tag + '\n' + (out.join('\n') || '(none)'));
};
scan('PRE-BOOT (イメージ読込直後)');
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); console.log('boot: no trap'); } catch (e) {
  console.log('boot: ' + e.message);
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
scan('POST-BOOT');
