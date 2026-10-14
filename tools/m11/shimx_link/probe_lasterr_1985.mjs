// unit 1..idx を順に実行し、各 unit の後の GetLastError() を出す。idx+1 unit 目は trace する (SHX-T9f #1985)。
// 出力: unit 入口の function_467c40 ゲート (P = Q(0x11e3af0), slot = Q(P)), 初期化フラグ 0x11f1114, GetLastError。
//   node probe_lasterr_1985.mjs <m11_*.cjs 絶対パス> [idx 既定 22] [trace 1 で unit idx+1 を trace]
// 注意: 0x11e3af0 等は LVA (VA - 0x400000)。VA 形式 (0x15e3af0) で読むと別の場所を読む。
import fs from 'fs';
const cjs = process.argv[2];
const idx = Number(process.argv[3] ?? 22);
const traceOn = Number(process.argv[4] ?? 1);
const M11 = new URL('../', import.meta.url).pathname;
const m2 = await import(cjs);
const image = fs.readFileSync(M11 + 'work/m11_image.bin');
const errs = [];
const mod = await (m2.default || m2)({ printErr: (s) => { errs.push(String(s)); } });
mod.HEAPU8.set(image, 0);
mod._m11_set_survey(1);
const sp = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) throw e; mod.__emscripten_stack_restore(sp); }
const sp0 = mod._emscripten_stack_get_current();
const gate = (n) => {
  const dv = new DataView(mod.HEAPU8.buffer);
  const p = dv.getBigUint64(0x11e3af0, true);
  const slot = p ? dv.getBigUint64(Number(p), true) : 0n;
  return `gate P=0x${p.toString(16)} slot=0x${slot.toString(16)} flag=${dv.getInt32(0x11f1114, true)}`;
};
const run = (i) => {
  try { return 'ret=' + mod._m11_call_unit(i); }
  catch (e) {
    try { mod.__emscripten_stack_restore(sp0); } catch (_) {}
    return 'exc=' + (e && e.m11_dllmain_done !== undefined ? 'halt0' : String((e && e.message) || e).split('\n')[0]);
  }
};
console.log('boot lasterr=' + mod._GetLastError());
for (let i = 0; i < idx; i++) {
  const r = run(i);
  console.log(`unit ${i + 1} ${r} lasterr=${mod._GetLastError()}`);
}
console.log(`before unit ${idx + 1}: ${gate()}`);
mod._m11_set_trace(1); if (mod._shimx_set_trace) mod._shimx_set_trace(traceOn);
const e0 = errs.length;
const r = run(idx);
console.log(`unit ${idx + 1} (trace) ${r} lasterr=${mod._GetLastError()}`);
for (const l of errs.slice(e0, e0 + 12)) console.log('  ' + l.slice(0, 200));
