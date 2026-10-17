// trap149_412c20_read_5280.mjs: trap149_412c20_probe_5280.py の変種 (stage4 ビルド済み) を survey と同じ呼び出しで走らせ、
// trap した unit ごとに function_4136a0 / function_412c20 / function_412e40 の entry 回数と arg1 を出す (#5280 受入 3・診断用)。
// 使い方: S4_NAME=t149 S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap149_412c20_read_5280.mjs > out.txt
// 出力は 1 行 'TRAP149_READ {...}' の JSON。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 't149');
const BASE = 0x11FF8500;
const SLOT = {
  e4136: 0, a4136: 8, c4136: 16, e412c: 24, a412c: 32, z412c: 40, z412c_ret: 48,
  a412e: 56, e412e: 64, site: 72, len4136: 80,
};
const SPAN = 88;
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const clr = () => mod.HEAPU8.fill(0, BASE, BASE + SPAN);
const read = () => {
  const dv = new DataView(mod.HEAPU8.buffer);
  const u = (k) => Number(dv.getBigUint64(BASE + SLOT[k], true));
  const h = (k) => '0x' + dv.getBigUint64(BASE + SLOT[k], true).toString(16);
  return {
    entry_4136a0: u('e4136'),
    arg1_4136a0_at_entry: h('a4136'),
    len_field_4136a0_at_entry: u('len4136'),
    call_4136a0_to_412c20: u('c4136'),
    entry_412c20: u('e412c'),
    arg1_412c20_at_entry: h('a412c'),
    arg1_lt1_412c20: u('z412c'),
    return_all_412c20: u('z412c_ret'),
    entry_412e40: u('e412e'),
    arg1_412e40_at_entry: h('a412e'),
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
  if (kind !== 'ok' || r.entry_412e40 > 0 || r.entry_412c20 > 0) out.push({ i, va: '0x' + BigInt(mod._m11_unit_va(i)).toString(16), kind, ...r });
}
console.log('TRAP149_READ ' + JSON.stringify({ units: out }));
