// trap_bins.mjs: unit の trap 時点の FastMM 空きリスト (bin 表) の状態を取る (#942 受入 1・2)。
// bin 表: BASE + 16*k の +8 = bin ポインタ P、P+24 = 先頭空きブロック F。FastMM_GetMem (function_407a50__lifted) は
// F-8 を読むため、F-8 が線形メモリ外なら trap する。
// 使い方: S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin UNIT=17 node tools/m11/ldfix/trap_bins.mjs
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 'fix');
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const MEM = BigInt(mod.HEAPU8.length);
const BASE = 16404744;
const scan = (tag) => {
  const d = new DataView(mod.HEAPU8.buffer); const out = [];
  for (let k = 0; k < 256; k++) {
    const rbx = BASE + 16 * k;
    const P = d.getBigUint64(rbx + 8, true);
    if (P < 8n || P + 32n >= MEM) continue;
    const F = d.getBigUint64(Number(P) + 24, true);
    const bad = F !== 0n && (F < 8n || F >= MEM);
    out.push(`k${k} P=0x${P.toString(16)} F=0x${F.toString(16)}${bad ? ' OOB' : ''}`);
  }
  console.log(tag + '\n' + (out.join('\n') || '(none)'));
};
const unit = +(process.env.UNIT || 17);
scan('BEFORE unit ' + unit);
try { mod._m11_call_unit(unit); console.log('unit ' + unit + ' no trap'); } catch (e) { console.log('unit ' + unit + ' TRAP: ' + e.message); }
mod.__emscripten_stack_restore(sp0);
scan('AFTER unit ' + unit);
