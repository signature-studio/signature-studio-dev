// #881: [G]+188 (=list, 0x11f7254 の実アドレス) の書込みを全 942 unit で追う (survey_units.mjs と同順)。
// 出力: list が変化した unit と変化後の値。list は unit 0..274 で 0 のままか, どの unit で初めて非 0 になるかを見る。
// 使い方: node trap_triage/probe881_watch.mjs
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const G = 0x11e4c80;
const m2 = await import(M11 + '/work/m11_boot.cjs');
const mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const u64 = (a) => new DataView(mod.HEAPU8.buffer).getBigUint64(a, true);
const hex = (x) => '0x' + BigInt(x).toString(16);
const listAddr = () => Number(u64(G)) + 188;
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
let prev = u64(listAddr());
console.log('before boot-units: obj=', hex(u64(G)), 'list(obj+188)=', hex(prev));
for (let i = 0; i < 942; i++) {
  const r = run(i);
  const cur = u64(listAddr());
  if (cur !== prev) console.log('unit', i, 'result', r, 'list', hex(prev), '->', hex(cur));
  prev = cur;
}
console.log('final list=', hex(prev), 'obj=', hex(u64(G)));
