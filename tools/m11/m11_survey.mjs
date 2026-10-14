// M11 unit survey: InitUnits ループを抑止し, 942 unit の Init を 1 本ずつ try/catch で隔離実行する (trap 後は shadow stack を復元)
// #513: unit ごとに VirtualAlloc 累計上限 (M11_VA_UNIT_BUDGET_MB, 既定 256) を掛け, unit 実行中に VirtualAlloc が NULL (OOM) を返した
//       trap を 'oom' に分類する. image 領域を壊した unit (InitTable 破壊) は実行前の image を戻して 'clobber' に分類する.
// 環境変数: M11_SURVEY_UNITS=<path> (unit 別ラベル JSON) / M11_SURVEY_COST=<path> (unit 別 VA・GetMem 消費 JSON) / M11_SURVEY_STACK=<i,..> (その unit の trap スタック)
//           M11_VFREE_NOOP=1 (VirtualFree を実解放しない = NC) / M11_VA_UNIT_BUDGET_MB=0 (上限なし = 旧挙動) / M11_VA_BIGTRACE=1 / M11_VA_STACK_AT=<n>
import fs from 'fs';
import { ptrPre, ptrCheck } from './m11_ptrcheck.mjs';
const M11 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const errs = [];
if (process.env.M11_SURVEY_STACK || process.env.M11_VA_STACK_AT) Error.stackTraceLimit = 64;   // 関数名は m11_wasmnames.py で注釈
const mod = await m2.default({ printErr: (s) => { errs.push(String(s)); } });
const img = fs.readFileSync(M11 + '/work/m11_image.bin');
mod.HEAPU8.set(img, 0);
const ptrPreSet = ptrPre(mod, img.length);
mod._m11_set_survey(1);
if (process.env.M11_VFREE_NOOP === '1') mod._m11_set_vfree_noop(1);
if (process.env.M11_VA_STACK_AT) mod._m11_set_va_stack_at(Number(process.env.M11_VA_STACK_AT));
if (process.env.M11_VA_BIGTRACE === '1') mod._m11_set_va_bigtrace(1);
const budgetMb = Number(process.env.M11_VA_UNIT_BUDGET_MB ?? '256');
mod._m11_set_va_unit_budget(budgetMb);
const sp_boot = mod._emscripten_stack_get_current();
let bootThrew = null, done = false;
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) { done = true; mod.__emscripten_stack_restore(sp_boot); }
  else bootThrew = (e && e.message) || String(e);
}
const res = { ok: 0, noproc: 0, miss: 0, trap: 0, clobber: 0 };
const kinds = {}, kindsNonOom = {}, topFrames = {}, halted = [];
let trapOom = 0, okWithOom = 0;
const perUnitCost = [];                // unit ごとの VirtualAlloc 確保バイト増分 / GetMem・FreeMem probe 増分 / OOM 回数
const oomUnits = [], bigUnits = [], clobberUnits = [];   // bigUnits: 64MB 以上の VirtualAlloc を要求した unit ('0x..:ok|trap:回数')
const sp0 = mod._emscripten_stack_get_current();
const first = [];
const perUnit = [];
const detail = [];                     // M11_SURVEY_DETAIL: unit 別の kind と trap 種別 (oob / halt0 / unreachable)
const hex = (i) => '0x' + mod._m11_unit_va(i).toString(16);
// clobber 検出: InitTable (unit 先頭と末尾の proc VA) が実行前と同じか. 壊れたら unit 実行前の image (先頭 image.length B) を書き戻す
const unitVa0 = [mod._m11_unit_va(0), mod._m11_unit_va(941)];
const snap = new Uint8Array(img.length);
const tableIntact = () => mod._m11_unit_va(0) === unitVa0[0] && mod._m11_unit_va(941) === unitVa0[1];
for (let i = 0; i < 942; i++) {
  const va = hex(i);
  snap.set(mod.HEAPU8.subarray(0, img.length));
  mod._m11_va_unit_begin();
  const oom0 = Number(mod._m11_va_oom()), big0 = Number(mod._m11_va_big());
  const vaUsed0 = Number(mod._m11_va_used()), gm0 = Number(mod._m11_probe_count(0)), fm0 = Number(mod._m11_probe_count(1));
  const lf0 = Number(mod._m11_probe_count(6)), lr0 = Number(mod._m11_probe_count(7)), p413_0 = process.env.M11_INSTR_413060 === '1' ? Number(mod._m11_probe_count(8)) : 0;
  let r, err = null;
  try { r = mod._m11_call_unit(i); } catch (e) { err = e; }
  const clob = !tableIntact();
  if (clob) { mod.HEAPU8.set(snap, 0); }
  const hadOom = Number(mod._m11_va_oom()) > oom0;
  perUnitCost.push({ i, va, va_bytes: Number(mod._m11_va_used()) - vaUsed0, getmem: Number(mod._m11_probe_count(0)) - gm0,
    freemem: Number(mod._m11_probe_count(1)) - fm0, oom: Number(mod._m11_va_oom()) - oom0, clobber: clob,
    listfind: Number(mod._m11_probe_count(6)) - lf0, listraise: Number(mod._m11_probe_count(7)) - lr0, ...(p413_0 || process.env.M11_INSTR_413060 === '1' ? { f413060: Number(mod._m11_probe_count(8)) - p413_0 } : {}) });
  if (Number(mod._m11_va_big()) > big0) bigUnits.push(va + ':' + (err ? 'trap' : 'ok') + ':' + (Number(mod._m11_va_big()) - big0));
  if (process.env.M11_SURVEY_STACK && process.env.M11_SURVEY_STACK.split(',').includes(String(i))) console.error('[survey][stack] unit ' + i + ' ' + va + (clob ? ' (clobber)' : '') + ': ' + (err ? ((err && err.stack) || err) : 'returned ' + r));
  if (clob) {
    res.clobber++; clobberUnits.push(va); perUnit.push('clobber'); detail.push({ i, va, kind: 'clobber' });
    if (err) mod.__emscripten_stack_restore(sp0);
    continue;
  }
  if (!err) {
    perUnit.push(r === 1 ? 'ok' : r === 0 ? 'noproc' : r === 2 ? 'miss' : 'r' + r);
    detail.push({ i, va, kind: perUnit[perUnit.length - 1], ret: r });
    if (r === 1) res.ok++; else if (r === 0) res.noproc++; else if (r === 2) res.miss++;
    if (hadOom) { okWithOom++; oomUnits.push(va); }
    continue;
  }
  const e = err;
  res.trap++;
  perUnit.push(hadOom ? 'oom' : 'trap');
  if (hadOom) { trapOom++; oomUnits.push(va); }
  let k;
  if (e && e.m11_dllmain_done !== undefined) { k = 'halt0->longjmp (unit が Halt を呼んだ)'; halted.push(va); }
  else k = ((e && e.message) || String(e)).split('\n')[0];
  detail.push({ i, va, kind: hadOom ? 'oom' : 'trap', trap: k });
  kinds[k] = (kinds[k] || 0) + 1;
  if (!hadOom) kindsNonOom[k] = (kindsNonOom[k] || 0) + 1;
  const m = e && e.stack && /wasm-function\[(\d+)\]/.exec(e.stack);
  if (m) topFrames[m[1]] = (topFrames[m[1]] || 0) + 1;
  if (first.length < 12) first.push(va);
  mod.__emscripten_stack_restore(sp0);
}
if (process.env.M11_SURVEY_UNITS) fs.writeFileSync(process.env.M11_SURVEY_UNITS, JSON.stringify(perUnit));
if (process.env.M11_SURVEY_DETAIL) fs.writeFileSync(process.env.M11_SURVEY_DETAIL, JSON.stringify(detail));
if (process.env.M11_SURVEY_COST) fs.writeFileSync(process.env.M11_SURVEY_COST, JSON.stringify(perUnitCost));
if (process.env.M11_DEST_REC_OUT && process.env.M11_INSTR_413060 === '1') {
  const n = Number(mod._m11_dest_obs_n()), recs = [];
  for (let k = 0; k < Math.min(n, 512); k++) recs.push({ k, st: mod._m11_dest_rec(k, 0), len: mod._m11_dest_rec(k, 1), rc: mod._m11_dest_rec(k, 2), h: (mod._m11_dest_rec(k, 3) >>> 0).toString(16).padStart(8, '0') + (mod._m11_dest_rec(k, 4) >>> 0).toString(16).padStart(8, '0') });
  fs.writeFileSync(process.env.M11_DEST_REC_OUT, JSON.stringify(recs));
}
const topBy = (k) => perUnitCost.filter((c) => c[k] > 0).sort((a, b) => b[k] - a[k]).slice(0, 8).map((c) => c.va + ':' + c.i + ':' + c[k]);
const ff = {};
for (const l of errs) { const m = /unresolved function call: (\S+)/.exec(l); if (m) ff[m[1]] = (ff[m[1]] || 0) + 1; }
const stubs = [];
for (let i = 0; i < (mod._m11_stub_uniq() || 0); i++) stubs.push(mod.UTF8ToString(mod._m11_stub_name(i)) + ':' + mod._m11_stub_count(i));
const ptrcheck = ptrCheck(mod, ptrPreSet);
console.log('M11_SURVEY ' + JSON.stringify({
  ptrcheck,
  dllmain_done: done, boot_threw: bootThrew, units: 942, ...res, trap_oom: trapOom, trap_other: res.trap - trapOom, ok_with_oom: okWithOom,
  oom_units: oomUnits.slice(0, 60), clobber_units: clobberUnits, big_units: bigUnits.slice(0, 40), top_va_units: topBy('va_bytes'), top_getmem_units: topBy('getmem'),
  trap_kinds: kinds, trap_kinds_nonoom: kindsNonOom, top_frame_idx: topFrames,
  failfast_functions: ff, halted_units: halted.slice(0, 20), first_trap_units: first,
  getmem: Number(mod._m11_probe_count(0)), freemem: Number(mod._m11_probe_count(1)),
  ...(process.env.M11_INSTR_413060 === '1' ? {
    ...(mod._m11_dest_obs_n ? { dest_obs_n: Number(mod._m11_dest_obs_n()), dest_obs_hash: Number(mod._m11_dest_obs_hhi()).toString(16).padStart(8, '0') + Number(mod._m11_dest_obs_hlo()).toString(16).padStart(8, '0') } : {}),
    f413060_calls: Number(mod._m11_probe_count(8)), f413060_units: perUnitCost.filter((c) => c.f413060 > 0).map((c) => c.i + ':' + c.va + ':' + c.f413060),
  } : {}),
  fastmm_getmem_impl: Number(mod._m11_probe_count(2)), fastmm_freemem_impl: Number(mod._m11_probe_count(3)),
  va_calls: Number(mod._m11_va_calls()), va_bytes: Number(mod._m11_va_used()),
  va_live: Number(mod._m11_va_live()), va_peak: Number(mod._m11_va_peak()), va_oom: Number(mod._m11_va_oom()), va_denied: Number(mod._m11_va_denied()),
  va_freed: Number(mod._m11_va_freed()), va_freed_bytes: Number(mod._m11_va_freed_bytes()), va_free_unknown: Number(mod._m11_va_free_unknown()),
  va_free_skipped: Number(mod._m11_va_free_skipped()), va_decommit: Number(mod._m11_va_decommit()), va_big: Number(mod._m11_va_big()),
  vfree_noop: process.env.M11_VFREE_NOOP === '1', va_unit_budget_mb: budgetMb,
  icall_miss: mod._m11_icall_miss(), icall_miss_uniq: mod._m11_icall_miss_uniq(),
  stub_total: mod._m11_stub_total(), stub_uniq: mod._m11_stub_uniq(), stub_hits: stubs,
}));
