// unit idx (0 始まり) の直前で 0x11f1114 (初期化フラグ)・Q(6712) (vmtNewInstance dispatch 元)・slot 0x11f10e0 を読み、unit idx+1 を trace する (SHX-T9f #1985)。
//   node probe_flag_1985.mjs <m11_sx_*.cjs | m11_boot.cjs 絶対パス> [unit_index 既定 22]
//   素材: tools/m11/work/ (work-m11・gitignore)。
import fs from 'fs';
const cjs = process.argv[2];
const idx = Number(process.argv[3] ?? 22);
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
for (let i = 0; i < idx; i++) { try { mod._m11_call_unit(i); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) { try { mod.__emscripten_stack_restore(sp0); } catch (_) {} } } }
const dv = new DataView(mod.HEAPU8.buffer);
console.log('Q(6712)=0x' + dv.getBigUint64(6712, true).toString(16));
console.log('before unit', idx + 1, 'flag(0x11f1114)=', dv.getInt32(0x11f1114, true), 'slot(0x11f10e0)=0x' + dv.getBigUint64(0x11f10e0, true).toString(16));
mod._m11_set_trace(1); if (mod._shimx_set_trace) mod._shimx_set_trace(1);
const e0 = errs.length;
let res;
try { res = 'ret=' + mod._m11_call_unit(idx); }
catch (e) { res = 'exc=' + (e && e.m11_dllmain_done !== undefined ? 'halt0' : String((e && e.message) || e).split('\n')[0]); }
console.log(res);
for (const l of errs.slice(e0)) console.log(l.slice(0, 300));
