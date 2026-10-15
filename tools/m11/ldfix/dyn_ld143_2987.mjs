// dyn_ld143_2987.mjs — #2987 (LD-143): ddf630 の CELL_DEEP 2 セル X (LVA 0x11e2318・0x11e3c70) の内容 V と、
//   V の指す先 [V] の値を、静的イメージ・survey 経路 (942 unit の Init を隔離実行) の後・実 boot の後で読む。
//   機械語は `mov rax,[rip+X]` → `mov rax,[rax]` → `cmp dword [rax+0x14],0` の 2 段。IR は 1 段 (V を object とする)。
//   修復 (fix_spill_deep_2987.py) は [V] を object とする。よって [V] = 0 なら消費者は [0+0x14] を読む (u32_at_deref_plus14)。
//   survey は m11_survey.mjs と同じ呼び方 (set_survey・va_unit_budget 256・unit ごとの va_unit_begin)。
// 使い方: M11_WORK=<tools/m11/work の絶対パス> node dyn_ld143_2987.mjs   (既定は ../work/。work-m11 の展開が必要)
import fs from 'fs';
const WORK = process.env.M11_WORK || new URL('../work/', import.meta.url).pathname;
const CELLS = [0x11e2318, 0x11e3c70];
const img = fs.readFileSync(WORK + '/m11_image.bin');
const hx = (v) => '0x' + v.toString(16);
async function instance() {
  const m2 = await import(WORK + '/m11_boot.cjs');
  const errs = [];
  const mod = await m2.default({ printErr: (s) => errs.push(String(s)) });
  mod.HEAPU8.set(img, 0);
  return { mod, errs };
}
function snapCells(mod) {
  const dv = new DataView(mod.HEAPU8.buffer);
  return CELLS.map((X) => {
    const V = Number(dv.getBigUint64(X, true));
    const vOk = V > 0 && V + 0x18 <= dv.byteLength;
    const D = vOk ? Number(dv.getBigUint64(V, true)) : null;
    const dOk = D !== null && D + 0x18 <= dv.byteLength;
    return { X: hx(X), V: hx(V), deref: D === null ? null : hx(D),
      u32_at_V_plus14: vOk ? dv.getUint32(V + 0x14, true) : null,
      u32_at_deref_plus14: dOk ? dv.getUint32(D + 0x14, true) : null };
  });
}
function staticCells() {
  return CELLS.map((X) => {
    const V = Number(img.readBigUInt64LE(X));
    const D = V + 0x8 <= img.length ? Number(img.readBigUInt64LE(V)) : null;
    return { X: hx(X), V: hx(V), deref: D === null ? null : hx(D) };
  });
}
function realBoot(mod) {
  let threw = null, done = false;
  try { mod._m11_boot_enter(0n, 1n); } catch (e) {
    if (e && e.m11_dllmain_done !== undefined) done = true; else threw = (e && e.message) || String(e);
  }
  return { threw, dllmain_done: done, boot_stage: Number(mod._m11_boot_stage()), init_count: Number(mod._m11_init_count()),
    units_run: Number(mod._m11_units_run()), initunits_probe: Number(mod._m11_probe_count(4)), cells: snapCells(mod) };
}
function surveyRun(mod) {
  mod._m11_set_survey(1);
  const hasBudget = typeof mod._m11_set_va_unit_budget === 'function';
  if (hasBudget) mod._m11_set_va_unit_budget(256);
  const sp0 = mod._emscripten_stack_get_current();
  try { mod._m11_boot_enter(0n, 1n); } catch (e) {
    if (!(e && e.m11_dllmain_done !== undefined)) throw e;
    mod.__emscripten_stack_restore(sp0);
  }
  const afterBoot = snapCells(mod);
  const n = Number(mod._m11_units_total());
  let prev = JSON.stringify(afterBoot), traps = 0;
  const changes = [];
  const hasUnitBegin = typeof mod._m11_va_unit_begin === 'function';
  for (let i = 0; i < n; i++) {
    const sp = mod._emscripten_stack_get_current();
    if (hasUnitBegin) mod._m11_va_unit_begin();
    try { mod._m11_call_unit(i); } catch (e) { traps++; mod.__emscripten_stack_restore(sp); }
    const s = JSON.stringify(snapCells(mod));
    if (s !== prev) { changes.push({ unit: i, cells: JSON.parse(s) }); prev = s; }
  }
  return { after_boot: afterBoot, units_total: n, va_budget_export: hasBudget, unit_begin_export: hasUnitBegin, traps, changes, final: JSON.parse(prev) };
}
const t0 = Date.now();
const a = await instance();
const real = realBoot(a.mod);
const b = await instance();
const survey = surveyRun(b.mod);
console.log('PROBE143 ' + JSON.stringify({ static: staticCells(), real_boot: real, survey, ms: Date.now() - t0 }));
