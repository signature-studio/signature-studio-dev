// GUI-3 (#174): m11 + GUI shim の実行ハーネス (node)。
//   node run.mjs [--survey] [--out result.json] [--wasm path.cjs]
//   既定: DllMain attach (通常起動) を実行し、shim に到達した GUI API (GUI-REACH) と未実装 API (FAIL-FAST) を回収する。
//   --survey: m11_survey.mjs と同じく InitUnits を抑止して 942 unit を 1 本ずつ隔離実行 (未実装 API に当たった unit は例外で脱出し次へ)。VA 上限は既定 256 MiB (m11_survey.mjs と同じ既定。M11_VA_UNIT_BUDGET_MB で変更可)。
// 出力: 標準出力に FLGUI_RESULT <json>。--out で同じ JSON をファイルへ。常に exit 0 (判定は judge.py)。
import fs from 'fs';
import path from 'path';
const HERE = path.dirname(new URL(import.meta.url).pathname);
const M11 = process.env.GF_M11 || path.resolve(HERE, '../../m11');
const args = process.argv.slice(2);
const survey = args.includes('--survey');
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const wasmCjs = path.resolve(opt('--wasm', path.resolve(HERE, '../work/flengine/m11_gui.cjs')));
const outFile = opt('--out', null);

const errs = [];
const m2 = await import(wasmCjs);
const mod = await (m2.default ? m2.default({ printErr: (s) => { errs.push(String(s)); } }) : m2());
const img = fs.readFileSync(M11 + '/work/m11_image.bin');
mod.HEAPU8.set(img, 0);
const num = (f) => { try { return Number(f()); } catch (_) { return null; } };
const isDone = (e) => e && e.m11_dllmain_done !== undefined;
const msg1 = (e) => ((e && e.message) || String(e)).split('\n')[0];

let bootThrew = null, bootFailfast = null, dllmainDone = false;
const sp_boot = mod._emscripten_stack_get_current();
if (survey) { mod._m11_set_survey(1); mod._m11_set_va_unit_budget(Number(process.env.M11_VA_UNIT_BUDGET_MB ?? '256')); }
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (isDone(e)) { dllmainDone = true; if (survey) mod.__emscripten_stack_restore(sp_boot); }
  else if (e && e.gui_failfast) bootFailfast = e.gui_failfast;
  else bootThrew = msg1(e);
}

const res = { ok: 0, noproc: 0, miss: 0, trap: 0, clobber: 0 };
const kinds = {}, ffUnits = {}, perUnit = [];
if (survey) {   // m11_survey.mjs と同じ隔離プロトコル: unit ごとに VA 予算を開始し, InitTable が壊れたら実行前の image を戻して clobber に数える
  const sp0 = mod._emscripten_stack_get_current();
  const unitVa0 = [mod._m11_unit_va(0), mod._m11_unit_va(941)];
  const tableIntact = () => mod._m11_unit_va(0) === unitVa0[0] && mod._m11_unit_va(941) === unitVa0[1];
  const snap = new Uint8Array(img.length);
  const only = process.env.GF_SURVEY_ONLY ? process.env.GF_SURVEY_ONLY.split(',').map(Number) : null;   // 単独再測用: 指定 unit だけを (boot 直後・前 unit 無しで) 実行
  const reset = process.env.GF_SURVEY_RESET === '1' ? new Uint8Array(mod.HEAPU8) : null;   // 各 unit を boot 直後の wasm 線形メモリの状態から始める (前 unit の副作用を断つ。JS 側の状態は対象外)
  const memBuf = () => (mod.wasmMemory ? mod.wasmMemory.buffer : mod.HEAPU8.buffer);
  res.mem_boot_bytes = memBuf().byteLength; res.mem_grown_units = 0;   // ALLOW_MEMORY_GROWTH で線形メモリが伸びた unit 数 (実行の前後で長さが増えた unit)
  for (const i of only ?? Array.from({ length: 942 }, (_, k) => k)) {
    if (reset) {
      if (mod._gui_reach_dump) mod._gui_reach_dump();   // 前 unit の到達 (wasm 内カウンタ) を errs へ退避してから戻す
      if (memBuf().byteLength > reset.length) new Uint8Array(memBuf()).fill(0, reset.length);   // 前 unit が伸ばした領域は boot 直後には存在しない (ゼロ埋め)
      mod.HEAPU8.set(reset, 0);
    }
    const mem0 = memBuf().byteLength;
    errs.push('GF-UNIT-BEGIN ' + i);
    snap.set(mod.HEAPU8.subarray(0, img.length));
    mod._m11_va_unit_begin();
    let r, err = null;
    try { r = mod._m11_call_unit(i); } catch (e) { err = e; }
    if (memBuf().byteLength > mem0) res.mem_grown_units++;
    if (!tableIntact()) { mod.HEAPU8.set(snap, 0); res.clobber++; perUnit.push([i, 'clobber']); if (err) mod.__emscripten_stack_restore(sp0); continue; }
    if (!err) {
      if (r === 1) res.ok++; else if (r === 0) res.noproc++; else if (r === 2) res.miss++;
      perUnit.push([i, r === 1 ? 'ok' : r === 0 ? 'noproc' : r === 2 ? 'miss' : 'ret' + r]);
      continue;
    }
    res.trap++;
    let k;
    if (isDone(err)) k = 'halt0->longjmp';
    else if (err.gui_failfast) { k = 'gui_failfast'; ffUnits[err.gui_failfast] = (ffUnits[err.gui_failfast] || 0) + 1; }
    else k = msg1(err);
    kinds[k] = (kinds[k] || 0) + 1;
    perUnit.push([i, 'trap', k]);
    mod.__emscripten_stack_restore(sp0);
  }
  res.mem_end_bytes = memBuf().byteLength;
  if (process.env.GF_SURVEY_UNITS) fs.writeFileSync(process.env.GF_SURVEY_UNITS, JSON.stringify(perUnit));
}

if (mod._gui_reach_dump) mod._gui_reach_dump();   // --base (shim 無し比較元) には無い
const reach = [];
for (const l of errs) {
  const m = /GUI-REACH (\d+) (\w+) (\d+) (IMPL|STUB) P(\S+)$/.exec(l);
  if (m) reach.push({ order: +m[1], name: m[2], calls: +m[3], kind: m[4], prio: m[5] });
}
const failfast = {}, softstub = {};
for (const l of errs) { const m = /SOFT-STUB: unimplemented Win32 API: (\w+)/.exec(l); if (m) softstub[m[1]] = (softstub[m[1]] || 0) + 1; }
for (const l of errs) { const m = /FAIL-FAST: unimplemented Win32 API: (\w+)/.exec(l); if (m) failfast[m[1]] = (failfast[m[1]] || 0) + 1; }
const stubs = [];
for (let i = 0; i < (num(mod._m11_stub_uniq) || 0); i++) stubs.push(mod.UTF8ToString(mod._m11_stub_name(i)) + ':' + mod._m11_stub_count(i));
const probeNames = JSON.parse(fs.readFileSync(M11 + '/work/boot_final3_probes.json', 'utf8'));
const probes = {};
probeNames.forEach((n, i) => { probes[n] = num(() => mod._m11_probe_count(i)); });
const sum = errs.find((l) => /GUI-REACH-SUMMARY/.test(l)) || null;
const result = {
  mode: survey ? 'survey' : 'boot',
  dllmain_done: dllmainDone, boot_threw: bootThrew, boot_failfast: bootFailfast,
  units_total: num(mod._m11_units_total), units_run: num(mod._m11_units_run), init_count: num(mod._m11_init_count),
  survey: survey ? { ...res, kinds, failfast_units: ffUnits } : null,
  reach, reach_summary: sum && sum.replace(/^.*GUI-REACH-SUMMARY /, ''),
  failfast_apis: failfast, softstub_apis: softstub, failfast_count: num(mod._gf_failfast_count),
  gui_icall_calls: num(mod._gf_icall_count), gui_ring_discarded: num(mod._gf_ring_discarded),
  icall_miss: num(mod._m11_icall_miss), icall_miss_uniq: num(mod._m11_icall_miss_uniq),
  icall_miss_targets: Array.from({ length: num(mod._m11_icall_miss_uniq) || 0 }, (_, i) => '0x' + (mod._m11_icall_miss_at(i) >>> 0).toString(16)),
  m11_stub_total: num(mod._m11_stub_total), m11_stubs: stubs, probes,
  va_calls: num(mod._m11_va_calls), va_bytes: num(mod._m11_va_used),
};
const json = JSON.stringify(result);
if (outFile) fs.writeFileSync(outFile, JSON.stringify(result, null, 1));
console.log('FLGUI_RESULT ' + json);
if (process.env.GF_LOG) fs.writeFileSync(process.env.GF_LOG, errs.join('\n') + '\n');
process.exit(0);
