// #5741: unit 275 の 80e040 の loop 内で, 864fe0 に渡す this と,
// 呼出し時点の list の count / base を記録する。864fe0 の入口 (icall ではない直接 call) は
// モジュールの関数テーブルを使わず, 80e040 の loop 上限 (eax) は [[G]]+188 の count を見る。
// 本 probe は list の値を 80e040 の直前 (8657d0 の後) と 864fe0 の trap 直前に読む。
// 使い方: node trap_triage/probe5741_loop275.mjs   (tools/m11 で実行)
import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
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
const dv = () => new DataView(mod.HEAPU8.buffer);
const hex = (x) => '0x' + Number(x).toString(16);
const u64 = (a) => dv().getBigUint64(a, true);
const u32 = (a) => dv().getUint32(a, true);
const G = 0x11e4c80;
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
for (let i = 0; i < 275; i++) run(i);
const obj = Number(u64(Number(u64(G))));
const list = Number(u64(obj + 0xbc));
console.log('before275 count=' + u64(list + 16).toString() + ' base=' + hex(u64(list + 8)));
// 275 の実行後, list の count が 2 になっているかを確認 (callback の Add が反映されたか)
console.log('unit 275 ->', run(275));
const obj2 = Number(u64(Number(u64(G))));
const list2 = Number(u64(obj2 + 0xbc));
console.log('after275 count=' + u64(list2 + 16).toString() + ' base=' + hex(u64(list2 + 8)));
console.log('mem[0x8]=' + hex(u64(8)) + ' mem[0x10]=' + hex(u64(16)) + ' mem[0x18]=' + hex(u64(24)));
