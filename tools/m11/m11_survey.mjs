// M11 unit survey: InitUnits ループを抑止し, 942 unit の Init を 1 本ずつ try/catch で隔離実行する (trap 後は shadow stack を復元)
import fs from 'fs';
const M11 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const errs = [];
const mod = await m2.default({ printErr: (s) => { errs.push(String(s)); } });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
let bootThrew = null, done = false;
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) { done = true; mod.__emscripten_stack_restore(sp_boot); }
  else bootThrew = (e && e.message) || String(e);
}
const res = { ok: 0, noproc: 0, miss: 0, trap: 0 };
const kinds = {}, topFrames = {}, halted = [];
const sp0 = mod._emscripten_stack_get_current();
const first = [];
for (let i = 0; i < 942; i++) {
  try {
    const r = mod._m11_call_unit(i);
    if (r === 1) res.ok++; else if (r === 0) res.noproc++; else if (r === 2) res.miss++;
  } catch (e) {
    res.trap++;
    let k;
    if (e && e.m11_dllmain_done !== undefined) { k = 'halt0->longjmp (unit が Halt を呼んだ)'; halted.push('0x' + mod._m11_unit_va(i).toString(16)); }
    else k = ((e && e.message) || String(e)).split('\n')[0];
    kinds[k] = (kinds[k] || 0) + 1;
    const m = e && e.stack && /wasm-function\[(\d+)\]/.exec(e.stack);
    if (m) topFrames[m[1]] = (topFrames[m[1]] || 0) + 1;
    if (first.length < 12) first.push('0x' + mod._m11_unit_va(i).toString(16));
    mod.__emscripten_stack_restore(sp0);
  }
}
const ff = {};
for (const l of errs) { const m = /unresolved function call: (\S+)/.exec(l); if (m) ff[m[1]] = (ff[m[1]] || 0) + 1; }
const stubs = [];
for (let i = 0; i < (mod._m11_stub_uniq() || 0); i++) stubs.push(mod.UTF8ToString(mod._m11_stub_name(i)) + ':' + mod._m11_stub_count(i));
console.log('M11_SURVEY ' + JSON.stringify({
  dllmain_done: done, boot_threw: bootThrew, units: 942, ...res, trap_kinds: kinds, top_frame_idx: topFrames,
  failfast_functions: ff, halted_units: halted.slice(0, 20), first_trap_units: first,
  getmem: Number(mod._m11_probe_count(0)), freemem: Number(mod._m11_probe_count(1)),
  fastmm_getmem_impl: Number(mod._m11_probe_count(2)), fastmm_freemem_impl: Number(mod._m11_probe_count(3)),
  va_calls: Number(mod._m11_va_calls()), va_bytes: Number(mod._m11_va_used()),
  icall_miss: mod._m11_icall_miss(), icall_miss_uniq: mod._m11_icall_miss_uniq(),
  stub_total: mod._m11_stub_total(), stub_uniq: mod._m11_stub_uniq(), stub_hits: stubs,
}));
