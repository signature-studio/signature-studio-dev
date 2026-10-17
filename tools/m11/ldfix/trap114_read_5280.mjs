// trap114_read_5280.mjs: trap114_probe_5280.py の変種 (stage4 ビルド済み) を survey と同じ呼び出しで走らせ、
// trap した unit ごとに function_4128b0__lifted の entry 時の global 値と、call site A/B の通過回数・最後の site を出す (#5280 受入 1・診断用)。
// 使い方: S4_NAME=t114 S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap114_read_5280.mjs > out.txt
//   出力は 1 行 'TRAP114_READ {...}' の JSON。site A = 元 IR の call function_412770(18787752) (IR 117917 相当)、
//   site B = call function_412770(18787456) (IR 118017 相当)。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 't114');
const BASE = 0x11FF8200;
const SLOT = { entry: 0, g0: 8, g1: 16, g2: 24, siteA: 32, siteB: 40, last: 48, hit4129be: 56, v4129be: 64, v412904: 72, v412978: 80 };
const SPAN = 88;
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const hx = (v) => '0x' + BigInt.asUintN(64, v).toString(16);
const clr = () => mod.HEAPU8.fill(0, BASE, BASE + SPAN);
const read = () => {
  const dv = new DataView(mod.HEAPU8.buffer);
  const u = (k) => dv.getBigUint64(BASE + SLOT[k], true);
  return {
    entry_hits: Number(u('entry')),
    entry_globals: { g18787760: hx(u('g0')), g18787504: hx(u('g1')), g18768032: hx(u('g2')) },
    site_A_hits: Number(u('siteA')),
    site_B_hits: Number(u('siteB')),
    last_site: { 0n: 'none', 1n: 'A', 2n: 'B' }[u('last')] ?? String(u('last')),
    br_4129be_hits: Number(u('hit4129be')),
    i8_18787504_at_4129be: Number(u('v4129be')),
    i8_18787504_at_412904: Number(u('v412904')),
    i8_18787504_at_412978: Number(u('v412978')),
  };
};
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
clr();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const out = [];
for (let i = 0; i < 942; i++) {
  clr();
  let kind = 'ok';
  try { mod._m11_call_unit(i); } catch (e) {
    const halt = !!(e && e.m11_dllmain_done !== undefined);
    kind = halt ? 'halt0->longjmp' : ((e && e.message) || String(e)).split('\n')[0];
    mod.__emscripten_stack_restore(sp0);
  }
  const r = read();
  if (kind !== 'ok' || r.entry_hits > 0) out.push({ i, va: hx(BigInt(mod._m11_unit_va(i))), kind, ...r });
}
console.log('TRAP114_READ ' + JSON.stringify({ units: out }));
