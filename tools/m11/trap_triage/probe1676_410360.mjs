import fs from 'fs';
const M11 = new URL('../', import.meta.url).pathname.replace(/\/$/, '');
let mod = null;
const dv = () => new DataView(mod.HEAPU8.buffer);
const u64 = (a) => dv().getBigUint64(a, true);
const i32 = (a) => dv().getInt32(a, true) >>> 0;
const hex = (x) => '0x' + BigInt(x).toString(16);
const img = fs.readFileSync(M11 + '/work/m11_image.bin');
const m2 = await import(M11 + '/work/m11_boot.cjs');
mod = await m2.default({ printErr: () => {} });
mod.HEAPU8.set(img, 0);
mod._m11_set_survey(1);
const sp_boot = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (!(e && e.m11_dllmain_done !== undefined)) throw e;
  mod.__emscripten_stack_restore(sp_boot);
}
const sp0 = mod._emscripten_stack_get_current();
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
for (let i = 0; i < 114; i++) run(i);
const r = run(114);
const B = i32(0x11f7198);
const L = Number(u64(B + 188));
const vmt = Number(u64(L));
console.log('unit 114', r, 'list B', hex(L), 'rbx=[inst] (VMT)', hex(vmt));
for (const off of [0x30, 0x50]) {
  const a = vmt - off;
  const rt = Number(u64(a));
  const st = Number(img.readBigUInt64LE(a));
  console.log(`[VMT-0x${off.toString(16)}] @${hex(a)} runtime=${hex(rt)} image(static)=${hex(st)} VA=${hex(rt + 0x400000)} stub_byte=${rt ? hex(img[rt]) : '-'}`);
}
