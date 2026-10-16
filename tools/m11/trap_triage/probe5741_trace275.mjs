// #5741: unit 275 の実行中に 80e040 の入口・864fe0 の入口で list (=[[G]]+188) の base/count と this を記録する。
// 監視は m11_trace (icall 行) の代わりに、unit 275 の前後で list の値を読む。
// 使い方: node trap_triage/probe5741_trace275.mjs   (tools/m11 で実行)
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const lines = [];
const printErr = (s) => { s = String(s); if (s.includes('[m11][icall]') || s.includes('864fe0') || s.includes('80e040')) lines.push(s); };
const mod = await m2.default({ printErr });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const dv = () => new DataView(mod.HEAPU8.buffer);
const hex = (x) => '0x' + Number(x).toString(16);
const u64 = (a) => dv().getBigUint64(a, true);
const G = 0x11e4c80;
const snap = (tag) => {
  const obj = Number(u64(Number(u64(G))));
  const list = Number(u64(obj + 0xbc));
  console.log(tag, 'obj=' + hex(obj), 'list=' + hex(list), 'base=' + hex(u64(list + 8)), 'count=' + u64(list + 16).toString());
};
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
for (let i = 0; i < 275; i++) run(i);
snap('before275');
mod._m11_set_trace(1);
const r = run(275);
mod._m11_set_trace(0);
console.log('unit 275 ->', r);
snap('after275');
for (const l of lines.slice(-40)) console.log(l);
