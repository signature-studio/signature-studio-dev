import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
let mod = null;
let lastLine = '(start)';
const dv = () => new DataView(mod.HEAPU8.buffer);
const u64 = (a) => dv().getBigUint64(a, true);
const i32 = (a) => dv().getInt32(a, true) >>> 0;
const hex = (x) => '0x' + BigInt(x).toString(16);
let prev = null;
const snap = () => {
  const B = i32(0x11f7198);
  const L = Number(u64(B + 188));
  return { L, base: L ? u64(L + 8) : null, cnt: L ? u64(L + 16) : null };
};
const events = [];
const printErr = (s) => {
  if (!mod) return;
  const cur = snap();
  const key = (x) => JSON.stringify({ L: x.L, base: x.base === null ? null : String(x.base), cnt: x.cnt === null ? null : String(x.cnt) });
  if (prev && key(prev) !== key(cur)) {
    events.push(`after [${lastLine}] before [${s}]: L ${hex(prev.L)}->${hex(cur.L)} base ${prev.base === null ? '-' : hex(prev.base)}->${cur.base === null ? '-' : hex(cur.base)} cnt ${prev.cnt === null ? '-' : String(prev.cnt)}->${cur.cnt === null ? '-' : String(cur.cnt)}`);
  }
  prev = cur;
  lastLine = s;
};
const m2 = await import(M11 + '/work/m11_boot.cjs');
mod = await m2.default({ printErr });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
const target = Number(process.env.U || 114);
for (let i = 0; i < target; i++) run(i);
prev = snap();
console.log('before unit', target, JSON.stringify({ L: hex(prev.L), base: prev.base === null ? null : hex(prev.base), cnt: String(prev.cnt) }));
mod._m11_set_trace(1);
const r = run(target);
mod._m11_set_trace(0);
console.log('unit', target, r);
console.log(events.join('\n'));
