import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
const errs = [];
const m2 = await import(M11 + '/work/m11_boot.cjs');
const mod = await m2.default({ printErr: (s) => errs.push(s) });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const dv = () => new DataView(mod.HEAPU8.buffer);
const u64 = (a) => dv().getBigUint64(a, true);
const i32 = (a) => dv().getInt32(a, true) >>> 0;
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap:' + (e && e.message); } };
const state = () => { const B = i32(0x11f7198); const L = Number(u64(B + 188)); return { B, L, base: L ? u64(L + 8) : null, cnt: L ? u64(L + 16) : null }; };
const hex = (x) => (x === null ? 'null' : '0x' + BigInt(x).toString(16));
const target = Number(process.env.U || 114);
for (let i = 0; i < target; i++) run(i);
console.log('before', JSON.stringify(state(), (k, v) => typeof v === 'bigint' ? hex(v) : v));
mod._m11_set_trace(1);
const r = run(target);
mod._m11_set_trace(0);
console.log('unit', target, r, JSON.stringify(state(), (k, v) => typeof v === 'bigint' ? hex(v) : v));
console.log("stderr lines", errs.length); for (const e of errs) console.log("E " + e);
