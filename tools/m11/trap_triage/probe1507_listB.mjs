// #1507: callback が push する list B (G2=i32[0x11f7198], list=[G2+188]) のヘッダ (+8 base, +16 count) を unit 114 / 275 の前後で読む。
// callback 85df70 → 50a830(list, blk): base=[list+8], cnt=[list+16], [base+8*cnt]=blk, cnt++。 base=0 なら NULL 付近へ書く。
// 使い方: node trap_triage/probe1507_listB.mjs
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
const hex = (x) => '0x' + BigInt(x).toString(16);
const run = (i) => { try { return mod._m11_call_unit(i); } catch (e) { mod.__emscripten_stack_restore(sp0); return e && e.m11_dllmain_done !== undefined ? 'halt0' : 'trap'; } };
const u64 = (a) => dv().getBigUint64(a, true);
const i32 = (a) => dv().getInt32(a, true) >>> 0;
const snap = (tag) => {
  const B = i32(0x11f7198);
  const L = Number(u64(B + 188));
  if (!L) { console.log(tag, 'B list = 0'); return; }
  console.log(tag, 'B', hex(B), 'list', hex(L), 'hdr+0', hex(u64(L)), 'base(+8)', hex(u64(L + 8)), 'cnt(+16)', u64(L + 16).toString(), 'mem[0]', hex(u64(0)), 'mem[8]', hex(u64(8)), 'mem[16]', hex(u64(16)));
};
snap('init');
for (let i = 0; i < 276; i++) {
  if (i === 114 || i === 275) snap('before' + i);
  const r = run(i);
  if (i === 114 || i === 275) { snap('after' + i); console.log('  unit', i, r); }
}
