// bin_post_probe.mjs: bin 表 k184/185/186/215/236 の P/F を boot 前後で取る (#942 受入 2・書き込み元の切り分け)。
// 使い方: S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/bin_post_probe.mjs
// bin_table_pre_boot.mjs と違い、boot の trap 後も DataView を取り直して読む (detached ArrayBuffer 回避)。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 'fix');
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const BASE = 16404744;
const MEM = BigInt(mod.HEAPU8.length);
const dump = (tag) => {
  const d = new DataView(mod.HEAPU8.buffer);
  const out = [];
  for (const k of [184, 185, 186, 215, 236]) {
    const P = d.getBigUint64(BASE + 16 * k + 8, true);
    const F = P + 32n < MEM ? d.getBigUint64(Number(P) + 24, true) : -1n;
    out.push(`k${k} P=0x${P.toString(16)} F=0x${F.toString(16)}`);
  }
  console.log(tag + '\n' + out.join('\n'));
};
dump('PRE-BOOT');
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); console.log('boot: no trap'); } catch (e) {
  console.log('boot: ' + e.message);
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
dump('POST-BOOT');
