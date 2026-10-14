// trap_obj_942.mjs: survey と同じ呼び出しで、trap した unit ごとに probe_942_obj.py の記録 (entry 引数と [arg1+8]) を読む (#942 受入 1・2, 診断用)。
// 使い方: python3 probe_942_obj.py <base.ll> work/probe_942_obj.ll && bash stage4.sh work/probe_942_obj.ll probe_obj
//         S4_NAME=probe_obj S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_obj_942.mjs
// 記録は probe_942_obj.py の PROBE2_BASE (0x11FFE000)・SLOT2 (128 byte) 以降 (+8..+32 = 引数, +48 = 記録点の値)。unit ごとに領域を 0 にしてから呼ぶ。
import fs from 'fs';
const S4 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const M11 = S4 + '/work/stage4/' + (process.env.S4_NAME || 'probe_obj');
const PROBE2_BASE = 0x11FFE000;
const SLOT2 = 128;  // SITES の順番は probe_942_obj.py の SITES と一致させる
const SITES = ["function_8cbb00 entry", "function_8cbb00 before 418210 call (stack_var)", "function_418210 before 418190 call (*arg1)", "function_8cbcb0 entry"];
const m2 = await import(M11 + '/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(process.env.S4_IMAGE || (M11 + '/m11_image.bin')), 0);
const clr = () => mod.HEAPU8.fill(0, PROBE2_BASE, PROBE2_BASE + SITES.length * SLOT2);
const read = () => SITES.map((nm, k) => {
  const b = PROBE2_BASE + k * SLOT2;
  const dv = new DataView(mod.HEAPU8.buffer, b, SLOT2);
  const hits = Number(dv.getBigUint64(0, true));
  const hex = (o) => '0x' + dv.getBigUint64(o, true).toString(16);
  return hits ? { site: nm, hits, a1: hex(8), a2: hex(16), a3: hex(24), a4: hex(32), v48: hex(48) } : null;
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
console.log("TRAP_OBJ " + JSON.stringify({ units: out }));
