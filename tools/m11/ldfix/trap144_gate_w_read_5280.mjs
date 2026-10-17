// trap144_gate_w_read_5280.mjs: trap144_gate_w_probe_5280.py の計装版 stage4 で、gate 18825440 (0x11F40E0)・18825448 (0x11F40E8) を含む窓 [18825437, 18825451] (G=18825444) への書込みを読む (#5280 受入 2・診断用)。
// boot 中の書込み回数と直近 64 件 (site id・宛先・格納値)、各 unit の書込み回数の増分と、増分のあった unit の直近記録を出す。
// 使い方: S4_NAME=t144gw S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap144_gate_w_read_5280.mjs
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 't144gw');
const CNT = 0x11FFA000;
const RING = 0x11FFA100;
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const dv = () => new DataView(mod.HEAPU8.buffer);
const hx = (v) => '0x' + v.toString(16);
const cnt = () => Number(dv().getBigUint64(CNT, true));
// end: 書込み件数の絶対値 (CNT の値)。直近 n 件を新しい順に返す。
const ring = (end, n) => {
  const out = [];
  for (let k = 0; k < Math.min(n, 64, end); k++) {
    const idx = (end - 1 - k) & 63;
    const b = RING + idx * 32;
    out.push({ site: Number(dv().getBigUint64(b, true)), addr: hx(dv().getBigUint64(b + 8, true)), val: hx(dv().getBigUint64(b + 16, true)) });
  }
  return out;
};
// 全 store の宛先と格納値は ring の直近 64 件だけで、件数は CNT で数える。
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
const c0 = cnt();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const cBoot = cnt();
const bootRing = ring(cBoot, cBoot - c0);
const sp0 = mod._emscripten_stack_get_current();
const units = [];
for (let i = 0; i < 942; i++) {
  const pre = cnt();
  let kind = 'ok';
  try { mod._m11_call_unit(i); } catch (e) {
    const halt = !!(e && e.m11_dllmain_done !== undefined);
    kind = halt ? 'halt0->longjmp' : ((e && e.message) || String(e)).split('\n')[0];
    mod.__emscripten_stack_restore(sp0);
  }
  const post = cnt();
  if (kind !== 'ok' || post !== pre) units.push({ i, kind: kind.slice(0, 24), delta: post - pre, last: ring(post, post - pre).slice(0, 4) });
}
console.log('TRAP114_W ' + JSON.stringify({ boot_before: c0, boot_after: cBoot, boot_last: bootRing.slice(0, 8), units }));
