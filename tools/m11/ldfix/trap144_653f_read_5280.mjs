// trap144_653f_read_5280.mjs: trap144_653f_probe_5280.py の変種 (stage4 ビルド済み) を survey と同じ呼び出しで走らせ、
// trap した unit ごとに function_653f40 (dsp_ippv2.dll を function_6539e0 へ渡す関数) の entry 数・entry 時の global 18825448・
// 呼出し元 (function_65c540 / function_680610 の直接 call site 別) の通過回数を出す (#5280 受入 2・診断用)。
// 使い方: S4_NAME=t144f S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap144_653f_read_5280.mjs > out.txt
// 出力は 1 行 'TRAP144F_READ {...}' の JSON。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 't144f');
const BASE = 0x11FF8400;
const SLOT = {
  e653: 0, v653: 8, e65c: 16, s65c: 24, s680: 32, e680: 40,
  m1: 48, m2: 56, m3: 64, m4: 72, dsp: 80, cnt65c: 88,
};
const SPAN = 96;
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const clr = () => mod.HEAPU8.fill(0, BASE, BASE + SPAN);
const read = () => {
  const dv = new DataView(mod.HEAPU8.buffer);
  const u = (k) => Number(dv.getBigUint64(BASE + SLOT[k], true));
  return {
    entry_653f40: u('e653'),
    global_18825448_at_entry: '0x' + dv.getBigUint64(BASE + SLOT.v653, true).toString(16),
    entry_65c540: u('e65c'),
    call_65c540_to_653f40: u('s65c'),
    entry_680610: u('e680'),
    call_680610_to_653f40: u('s680'),
    call_680610_sites: { m1_2622504: u('m1'), m2_2622232_arg1: u('m2'), m3_2622232_arg16: u('m3'), m4_2622232_arg11: u('m4') },
    call_653f40_to_dsp: u('dsp'),
    counter_18825440_at_65c540: u('cnt65c'),
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
  if (kind !== 'ok' || r.entry_653f40 > 0 || r.entry_65c540 > 0) out.push({ i, va: '0x' + BigInt(mod._m11_unit_va(i)).toString(16), kind, ...r });
}
console.log('TRAP144F_READ ' + JSON.stringify({ units: out }));
