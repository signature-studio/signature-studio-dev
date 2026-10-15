// M11 e2e boot runner: m11_boot.cjs instantiation → m11_boot_enter (DllMain attach) → 実測数値 JSON 出力
// 環境変数 M11_TRACE=1 で icall / unit init をトレース
import fs from 'fs';
import { ptrPre, ptrCheck } from './m11_ptrcheck.mjs';
const M11 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const wasmSize = fs.statSync(M11 + '/work/m11_boot.cjs.wasm').size;
const m2 = await import(M11 + '/work/m11_boot.cjs');
const lines = [];
const mod = await (m2.default ? m2.default({ printErr: (s) => { lines.push(String(s)); console.error(String(s)); } }) : m2());
// PE イメージ (.text/.data/.rdata, LVA 座標) をホストが実行時に載せる (wasm には実バイナリを埋め込まない)
const img = fs.readFileSync(M11 + '/work/m11_image.bin');
mod.HEAPU8.set(img, 0);
const ptrPreSet = ptrPre(mod, img.length);
if (process.env.M11_TRACE === '1') mod._m11_set_trace(1);
if (process.env.M11_VFREE_NOOP === '1') mod._m11_set_vfree_noop(1);   // NC (#513): VirtualFree を実解放しない旧挙動
if (process.env.M11_VA_STACK_AT) mod._m11_set_va_stack_at(Number(process.env.M11_VA_STACK_AT));   // #513: N (>=1; 0 = 無効) 番目 (0 起算) の VirtualAlloc の呼出元スタックを出す
if (process.env.M11_VA_BIGTRACE === '1') mod._m11_set_va_bigtrace(1);   // #513: 64MB 以上の VirtualAlloc の呼出元 wasm スタックを stderr に出す
let rc, threw = null, dllmain_done = false;
try {
  rc = mod._m11_boot_enter(0n, 1n);
} catch (e) {
  if (e && e.m11_dllmain_done !== undefined) { rc = BigInt(e.m11_dllmain_done); dllmain_done = true; }
  else {
  threw = (e && e.message) || String(e);
  console.log('[e2e] boot threw:', threw);
  if (e && e.stack) console.log(e.stack.split('\n').slice(0, 12).join('\n'));
  }
}
const num = (f) => { try { return Number(f()); } catch (_) { return null; } };
const miss = [];
for (let i = 0; i < (num(mod._m11_icall_miss_uniq) || 0); i++) miss.push('0x' + (mod._m11_icall_miss_at(i) >>> 0).toString(16));
const probeNames = JSON.parse(fs.readFileSync(M11 + '/work/boot_final3_probes.json', 'utf8'));
const probes = {};
probeNames.forEach((n, i) => { probes[n] = num(() => mod._m11_probe_count(i)); });
const stubs = [];
for (let i = 0; i < (num(mod._m11_stub_uniq) || 0); i++) stubs.push(mod.UTF8ToString(mod._m11_stub_name(i)) + ':' + mod._m11_stub_count(i));
const ptrCheckRes = ptrCheck(mod, ptrPreSet);
console.log('M11_RESULT ' + JSON.stringify({
  wasm_size: wasmSize,
  image_bytes: img.length,
  boot_stage: num(mod._m11_boot_stage),
  init_count: num(mod._m11_init_count),
  va_used: num(mod._m11_va_used),
  va_calls: num(mod._m11_va_calls),
  va_live: num(mod._m11_va_live), va_peak: num(mod._m11_va_peak), va_oom: num(mod._m11_va_oom),
  va_freed: num(mod._m11_va_freed), va_free_unknown: num(mod._m11_va_free_unknown), va_big: num(mod._m11_va_big),
  icall_ok: num(mod._m11_icall_ok),
  icall_miss: num(mod._m11_icall_miss),
  icall_miss_uniq: num(mod._m11_icall_miss_uniq),
  icall_miss_targets: miss.slice(0, 64),
  units_total: num(mod._m11_units_total),
  units_run: num(mod._m11_units_run),
  units_skipped: num(mod._m11_units_skipped),
  disp_entries: num(mod._m11_disp_count),
  probes,
  stub_total: num(mod._m11_stub_total),
  stub_uniq: num(mod._m11_stub_uniq),
  stub_hits: stubs.slice(0, 80),
  dllmain_done,
  longjmp_hit: num(mod._m11_longjmp_hit),
  boot_rc: rc === undefined ? null : String(rc),
  threw,
  ptrcheck: ptrCheckRes,
}));
if (!ptrCheckRes.gate.pass) {   // #2778: ptrcheck ゲート不合格 (M11_PTRCHECK_MAX_NEW). JSON は出した後に非 0
  console.error('FAIL: ptrcheck image_va_words_new=' + ptrCheckRes.image_va_words_new + ' > max=' + ptrCheckRes.gate.max + ' (' + ptrCheckRes.gate.env + ')');
  process.exitCode = 1;
}
if (!ptrCheckRes.unremap.gate.pass) {   // #3113: 未 remap の疑い (分類 B) の基準不合格・分類ファイル欠落 (fail-closed)
  console.error('FAIL: ptrcheck unremap_cand=' + ptrCheckRes.unremap.unremap_cand + ' > max=' + ptrCheckRes.unremap.gate.max + ' (' + ptrCheckRes.unremap.gate.env + ', classes=' + ptrCheckRes.unremap.classes.file + ' available=' + ptrCheckRes.unremap.classes.available + ')');
  process.exitCode = 1;
}
