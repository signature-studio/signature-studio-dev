// trap114_g_read_5280.mjs: stage4 ビルド済み (LB=0 の m11_image.bin) で、global 18787504 (= 0x11EACB0・call site B の分岐値) を
// boot 終了時と各 unit の呼出し直前・直後で読む (#5280 受入 1 の残り・診断用)。
// 目的: 0x100000002 が boot で入って unit 間で残るか、unit の実行中に入るかを分ける。
// 使い方: S4_NAME=t114src S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap114_g_read_5280.mjs
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 't114src');
const G = 18787504;
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const hx = (v) => '0x' + v.toString(16);
const g = () => new DataView(mod.HEAPU8.buffer).getBigUint64(G, true);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
const gBoot0 = g();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const gBoot1 = g();
const sp0 = mod._emscripten_stack_get_current();
const out = [];
for (let i = 0; i < 942; i++) {
  const pre = g();
  let kind = 'ok';
  try { mod._m11_call_unit(i); } catch (e) {
    const halt = !!(e && e.m11_dllmain_done !== undefined);
    kind = halt ? 'halt0->longjmp' : ((e && e.message) || String(e)).split('\n')[0];
    mod.__emscripten_stack_restore(sp0);
  }
  const post = g();
  if (kind !== 'ok' || pre !== post) out.push({ i, kind: kind.slice(0, 24), pre: hx(pre), post: hx(post) });
}
console.log('TRAP114_G ' + JSON.stringify({ boot_before: hx(gBoot0), boot_after: hx(gBoot1), units: out }));
