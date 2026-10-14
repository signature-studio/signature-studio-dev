// trap_probe_942.mjs: survey と同じ呼び出しで、trap の瞬間の 6 関数の entry 引数を読む (#942 受入 1・2, 診断用)。
// 使い方: 先に python3 probe_942.py <base.ll> work/probe_942.ll && bash stage4.sh work/probe_942.ll probe
//         S4_NAME=probe S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_probe_942.mjs
// 記録は probe_942.py の PROBE_BASE (0x11FFF000)・SLOT (64 byte) 以降。unit ごとに領域を 0 にしてから呼ぶ。C 版 (m11_ov.c) の関数は記録されない。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 'probe');
const PROBE_BASE = 0x11FFF000;
const SLOT = 64;
const SITES = ["function_418190", "function_4133f0", "function_409c80", "function_407e20__lifted", "function_412e40", "function_8c6530", "function_412c20"];
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const clr = () => mod.HEAPU8.fill(0, PROBE_BASE, PROBE_BASE + 512);
const read = () => SITES.map((nm, k) => {
  const b = PROBE_BASE + k * SLOT;
  const dv = new DataView(mod.HEAPU8.buffer, b, SLOT);
  const hits = Number(dv.getBigUint64(0, true));
  const hex = (o) => '0x' + dv.getBigUint64(o, true).toString(16);
  return hits ? { site: nm, hits, a1: hex(8), a2: hex(16), a3: hex(24), ret: hex(32) } : null;
}).filter(Boolean);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const out = [];
for (let i = 0; i < 942; i++) {
  clr();
  try { mod._m11_call_unit(i); } catch (e) {
    if (!(e && e.m11_dllmain_done !== undefined)) {
      out.push({ i, va: "0x" + Number(mod._m11_unit_va(i)).toString(16), kind: ((e && e.message) || String(e)).split("\n")[0], sp: "0x" + mod._emscripten_stack_get_current().toString(16), probe: read() });
    }
    mod.__emscripten_stack_restore(sp0);
  }
}
console.log("TRAP_PROBE " + JSON.stringify({ units: out }));
