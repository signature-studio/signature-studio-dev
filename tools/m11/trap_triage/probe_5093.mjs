// #5093 (M11-32): unit 144 の trap 直前の UStrAsg (function_4133f0, m11_ov.c) 呼出しと [0x64] (refcount) を読む probe.
// 前提: tools/m11 で bash m11_gen_ir2.sh → bash m11_build.sh 済み (OFF)。素材 work-m11・fl-win64・[EMSDK]。
// usage: FL_WIN64_DIR=... EMSDK_HOME=... M11_DIR=$PWD node trap_triage/probe_5093.mjs
import fs from 'fs';
const M11 = process.env.M11_DIR;
const m2 = await import(M11 + '/work/m11_boot.cjs');
let mod = null;
const lines = [];
const rd = (a) => new DataView(mod.HEAPU8.buffer).getUint32(a, true);
mod = await m2.default({ printErr: (s) => { s = String(s); if (s.startsWith('[m11][UStrAsg]') || s.startsWith('[m11][icall]')) lines.push(s.trim() + ' | D(0x64)=' + rd(0x64).toString(16)); } });
Error.stackTraceLimit = 60;
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
mod._m11_set_va_unit_budget(256);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) { mod.__emscripten_stack_restore(sp_boot); }
const sp0 = mod._emscripten_stack_get_current();
for (let i = 0; i < 144; i++) { mod._m11_va_unit_begin(); try { mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); } }
console.log('before 144 D(0x64)=' + rd(0x64).toString(16));
mod._m11_va_unit_begin(); mod._m11_set_trace(1);
try { mod._m11_call_unit(144); console.log('no trap'); } catch (e) { console.log('TRAP ' + e); console.log(String(e.stack).split('\n').slice(1, 14).join('\n')); }
mod._m11_set_trace(0);
console.log(lines.join('\n'));
console.log('after D(0x64)=' + rd(0x64).toString(16));
