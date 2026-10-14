// bin_size_probe.mjs: boot 後の FastMM サイズ→bin 表 (IR の function_407a50 が読む 0x11e6a3c 付近) の値を取る (#942 受入 1・2)。
// 使い方: S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/bin_size_probe.mjs
// 出力: boot 直後 (PRE) と boot 後 (POST) について、表 326 バイトの相違数・最大 bin 番号・184 以上の参照数。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 'fix');
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const T = 18770492, N = 326;
const probe = (tag) => {
  const v = mod.HEAPU8.subarray(T, T + N);
  const nz = [...v].filter((x) => x !== 0).length;
  const max = Math.max(...v);
  const hi = [...v].filter((x) => x >= 184).length;
  console.log(`${tag}: nonzero=${nz} max_bin=${max} refs_ge184=${hi}`);
};
probe('PRE');
const sp = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); console.log('boot: no trap'); } catch (e) {
  console.log('boot: ' + e.message);
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp);
}
probe('POST');
