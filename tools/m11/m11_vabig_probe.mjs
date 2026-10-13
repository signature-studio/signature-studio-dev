// #513: 巨大 VirtualAlloc (unit 368 の 981000) の n = *(int32*)(*(u64*)VA 0x15e4080) の出所を実測する probe.
//   boot 後 / 指定 unit の直前・直後に slot (0x15e4080+LB) と、その指す先の int32 を読み、unit 実行中の VirtualAlloc 要求サイズ (stderr の [m11][VA-big]) を出す.
// 使い方: node m11_vabig_probe.mjs [unit=368] [--skip=101,144] [--watch=<hexaddr>,...]
//   --pre=<i,..>  : 対象 unit の前に実行する unit (その unit が slot を書くかの切り分け用)
import fs from 'fs';
const M11 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const LB = Number(process.env.M11_LB_BASE || 0);
const arg = (k) => { const a = process.argv.find((x) => x.startsWith('--' + k + '=')); return a ? a.slice(k.length + 3) : null; };
const unit = Number(process.argv.find((x) => /^\d+$/.test(x)) ?? 368);
const preArg = arg('pre') || '';
const pre = preArg.startsWith('0-') ? Array.from({ length: Number(preArg.slice(2)) + 1 }, (_, i) => i) : preArg.split(',').filter(Boolean).map(Number);   // '0-367' = survey と同じ順序で 0..367
const m2 = await import(M11 + '/work/m11_boot.cjs');
const errs = [];
const mod = await m2.default({ printErr: (s) => errs.push(String(s)) });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_survey(1);
mod._m11_set_va_unit_budget(Number(process.env.M11_VA_UNIT_BUDGET_MB ?? '1024'));
const sp = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) { mod.__emscripten_stack_restore(sp); }
const dv = () => new DataView(mod.HEAPU8.buffer);
const hx = (v) => '0x' + BigInt(v).toString(16);
const SLOT = 0x15e4080 + LB;
const snapshot = (label) => {
  const p = dv().getBigUint64(SLOT, true);
  let n = null, nb = null;
  if (p > 0n && p < BigInt(mod.HEAPU8.length - 4)) { n = dv().getInt32(Number(p), true); nb = Array.from(mod.HEAPU8.subarray(Number(p), Number(p) + 8)).map((b) => b.toString(16).padStart(2, '0')).join(' '); }
  console.log('PROBE ' + JSON.stringify({ at: label, slot: hx(SLOT), slot_value: hx(p), n_int32: n, bytes: nb, heap_bytes: mod.HEAPU8.length }));
};
const run = (i) => {
  const s = mod._emscripten_stack_get_current();
  let r = null, trap = null;
  try { r = mod._m11_call_unit(i); } catch (e) { trap = ((e && e.message) || String(e)).split('\n')[0]; mod.__emscripten_stack_restore(s); }
  return { unit: i, va: hx(mod._m11_unit_va(i)), ret: r, trap };
};
snapshot('after_boot');
let prevSlot = dv().getBigUint64(SLOT, true);
let prev0 = dv().getUint32(0, true);   // linear 0 の int32 (981000 の n は slot が 0 のとき *(int32*)0 を読む)
console.log('ADDR0 after_boot ' + hx(prev0));
for (const i of pre) {
  const r = run(i);
  const c0 = dv().getUint32(0, true);
  if (c0 !== prev0) { console.log('ADDR0_CHANGED_BY unit ' + i + ' ' + r.va + ' ' + hx(prev0) + ' -> ' + hx(c0)); prev0 = c0; }
  const cur = dv().getBigUint64(SLOT, true);
  if (cur !== prevSlot) { console.log('SLOT_CHANGED_BY unit ' + i + ' ' + r.va + ' ' + hx(prevSlot) + ' -> ' + hx(cur)); prevSlot = cur; }
}
console.log('PRE_DONE ' + pre.length + ' units');
snapshot('before_unit_' + unit);
for (const w of (arg('watch') || '').split(',').filter(Boolean)) { const a = Number(w) + LB; console.log('WATCH ' + w + ' int32=' + dv().getInt32(a, true) + ' u64=' + hx(dv().getBigUint64(a, true))); }
{ // 正しい RVA (VA 0x15e4080 - 0x400000 = 0x11e4080) 側の slot と、それが指す先の int32
  const rs = dv().getBigUint64(0x11e4080 + LB, true);
  const rn = rs > 0n && rs < BigInt(mod.HEAPU8.length - 4) ? dv().getInt32(Number(rs), true) : null;
  console.log('CORRECT_SLOT ' + JSON.stringify({ rva: hx(0x11e4080 + LB), value: hx(rs), n_int32: rn, image_len: fs.statSync(M11 + '/work/m11_image.bin').size }));
}
if (arg('poke') !== null) for (const kv of arg('poke').split(',')) { const [a, v] = kv.split('='); dv().setInt32(Number(a) + LB, Number(v), true); console.log('POKE int32 @' + a + ' = ' + v); }   // --poke=<addr>=<int32>,..
if (arg('poke0') !== null) { dv().setInt32(0, Number(arg('poke0')), true); console.log('POKE linear0 int32 = ' + arg('poke0')); }
console.log('MEM0 ' + JSON.stringify({ u32_at_0: dv().getUint32(0, true), i32_at_0: dv().getInt32(0, true), first16: Array.from(mod.HEAPU8.subarray(0, 16)).map((b) => b.toString(16).padStart(2, '0')).join(' ') }));
mod._m11_va_unit_begin();
const r = run(unit);
console.log('UNIT ' + JSON.stringify({ ...r, va_used: Number(mod._m11_va_used()), va_calls: Number(mod._m11_va_calls()), va_big: Number(mod._m11_va_big()) }));
snapshot('after_unit_' + unit);
for (const l of errs.filter((x) => /VA-big|VA\]/.test(x))) console.log('STDERR ' + l);
