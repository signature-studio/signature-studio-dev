// M11: survey と同じ手順で unit 0..K-1 を実行し, unit K の実行前後で image 領域 (m11_image.bin の長さ) がどれだけ変わったかを出す (#513, clobber 調査用)
// 使い方: node m11_unit_imgdiff.mjs <K> [VA 上限 MB = 256]   → 'IMGDIFF {...}' (変更バイト数・range 数・最初/最後の range・InitTable の無事)
import fs from 'fs';
const M11 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const K = Number(process.argv[2]);
const m2 = await import(M11 + '/work/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
const img = fs.readFileSync(M11 + '/work/m11_image.bin');
mod.HEAPU8.set(img, 0);
mod._m11_set_survey(1);
mod._m11_set_va_unit_budget(Number(process.argv[3] ?? '256'));
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) { mod.__emscripten_stack_restore(sp_boot); }
const sp0 = mod._emscripten_stack_get_current();
const va0 = [mod._m11_unit_va(0), mod._m11_unit_va(941)];
let before = null, err = null, vaK = 0;
for (let i = 0; i <= K; i++) {
  mod._m11_va_unit_begin();
  if (i === K) { before = mod.HEAPU8.slice(0, img.length); vaK = mod._m11_unit_va(K); }
  try { mod._m11_call_unit(i); } catch (e) { if (i === K) err = (e && e.message) || String(e); mod.__emscripten_stack_restore(sp0); }
}
const a = mod.HEAPU8, ranges = [];
let st = -1;
for (let k = 0; k < img.length; k++) {
  const d = a[k] !== before[k];
  if (d && st < 0) st = k;
  if (!d && st >= 0) { ranges.push([st, k]); st = -1; }
}
if (st >= 0) ranges.push([st, img.length]);
const hex = (r) => r[0].toString(16) + '-' + r[1].toString(16);
console.log('IMGDIFF ' + JSON.stringify({ unit: K, va: '0x' + vaK.toString(16), trap: err,
  changed_bytes: ranges.reduce((x, r) => x + r[1] - r[0], 0), ranges: ranges.length, first: ranges.slice(0, 3).map(hex), last: ranges.slice(-3).map(hex),
  inittable_intact: mod._m11_unit_va(0) === va0[0] && mod._m11_unit_va(941) === va0[1] }));
