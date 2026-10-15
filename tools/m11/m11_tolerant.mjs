// M11 寛容起動 (#2714 WIN-3): InitUnits の 942 unit を逐次に走らせ, 失敗 unit は skipped と記録して次へ進む.
// C 側 (m11_ov.c の g_tolerant) が InitUnits を JS の m11_tolerant_run に渡す. strict (m11_run.mjs) と survey (m11_survey.mjs) は変えない.
// 状態は unit 間で持ち越す (survey と違い image を戻さない). 失敗 unit の前後の image 差分は記録する (リスク評価用).
// 環境変数: M11_VA_UNIT_BUDGET_MB (既定 256, 0 = 上限なし; unit ごとの VirtualAlloc 累計上限 #513)
//           M11_TOLERANT_OUT=<path> (全 unit の記録 JSON・失敗 unit の image 差分)
import fs from 'fs';
import { ptrPre, ptrCheck } from './m11_ptrcheck.mjs';
const M11 = new URL('./', import.meta.url).pathname.replace(/\/$/, '');
const m2 = await import(M11 + '/work/m11_boot.cjs');
const errs = [];
let curUnit = -1;   // #3325: M11_TOLERANT_ERR=1 のとき [m11] の観測行に unit 番号を付ける
const mod = await m2.default({ printErr: (s) => { errs.push(String(s)); if (process.env.M11_TOLERANT_ERR && /^\[m11\]/.test(String(s))) console.error('[unit ' + curUnit + '] ' + s); } });
const img = fs.readFileSync(M11 + '/work/m11_image.bin');
mod.HEAPU8.set(img, 0);
const ptrPreSet = ptrPre(mod, img.length);
mod._m11_set_tolerant(1);
mod._m11_set_va_unit_budget(Number(process.env.M11_VA_UNIT_BUDGET_MB ?? '256'));
const snap = new Uint8Array(img.length);
const heapFrom = process.env.M11_HEAP_FROM;   // #2768: 寛容起動の記録 JSON (M11_TOLERANT_OUT の出力). その skipped unit だけ heap 全体の差分を取る (既定 off)
const heapSet = heapFrom ? new Set(JSON.parse(fs.readFileSync(heapFrom, 'utf8')).skipped.map((s) => s.i)) : null;
const heapRec = [];
const peekAddrs = (process.env.M11_TOLERANT_PEEK || '').split(',').filter(Boolean).map(Number);   // #3325: 計測用 (既定 off). unit 前後の u32 を読む
const peekUnits = process.env.M11_TOLERANT_PEEK_UNITS ? new Set(process.env.M11_TOLERANT_PEEK_UNITS.split(',').map(Number)) : null;
let hbuf = null, hLen = 0;
const units = [];                  // 全 unit: [i, va, kind, va_bytes, getmem, freemem, oom, clobber]
const skipped = [];                // 失敗 unit (skip): 種類・メッセージ・image 差分の範囲
const kinds = {};
const SKIP = new Set(['halt0', 'oob', 'unreachable', 'abort', 'other', 'oom', 'miss', 'clobber']);
let hookRan = false, started = 0, clobber = 0, okWithOom = 0, sp0 = 0;
const diffRanges = () => {   // 直前 unit の前後で image 範囲 (0..img.length) が変わった区間 (16B 以内の隙間は同じ区間)
  const cur = mod.HEAPU8, n = img.length, out = [];
  let i = 0;
  while (i < n) {
    if (cur[i] === snap[i]) { i++; continue; }
    const s = i; let e = i; i++;
    while (i < n && i - e <= 16) { if (cur[i] !== snap[i]) e = i; i++; }
    out.push([s, e + 1]);
  }
  return out;
};
const G = (n) => { const v = mod[n]; return Number(v !== null && typeof v === 'object' ? v.value : v); };
const LAY = heapSet ? { gb: G('___global_base'), sl: G('___stack_low'), sh: G('___stack_high'), hb: G('___heap_base') } : null;
const regionOf = (a) => (a < LAY.gb ? 'gap' : a < LAY.sl ? 'c_static' : a < LAY.sh ? 'stack' : a < LAY.hb ? 'stack_gap' : 'heap');
const heapDiff = () => {   // #2768: unit 直前の heap 全体 (hbuf) と現在の差分を, image の外で区間にする (16B 以内の隙間は同じ区間). 64KB (wasm の頁) 単位で比べてから byte を見る
  const cur = mod.HEAPU8, L1 = cur.length, L0 = hLen, out = [], zero = Buffer.alloc(65536);
  const view = (u8, o, n) => Buffer.from(u8.buffer, u8.byteOffset + o, n);
  let cs = -1, ce = -1;
  const add = (i) => { if (cs >= 0 && i - ce <= 16) ce = i + 1; else { if (cs >= 0) out.push([cs, ce, regionOf(cs)]); cs = i; ce = i + 1; } };
  for (let p = 0; p < L1; p += 65536) {
    const n = Math.min(65536, L1 - p);
    if (view(cur, p, n).equals(p < L0 ? view(hbuf, p, n) : view(zero, 0, n))) continue;
    for (let k = 0; k < n; k++) if (p + k >= img.length && cur[p + k] !== (p < L0 ? hbuf[p + k] : 0)) add(p + k);
  }
  if (cs >= 0) out.push([cs, ce, regionOf(cs)]);
  return out;
};
mod.m11_tolerant_run = () => {   // C の function_4120c0 (g_tolerant) から呼ばれる: InitUnits 本体
  hookRan = true;
  const count = Number(mod._m11_tol_count()), base = Number(mod._m11_tol_units());
  sp0 = Number(mod._emscripten_stack_get_current());
  const va0 = count ? mod._m11_unit_va(0) : 0, vaL = count ? mod._m11_unit_va(count - 1) : 0;
  const intact = () => mod._m11_unit_va(0) === va0 && (!count || mod._m11_unit_va(count - 1) === vaL);
  for (let i = 0; i < count; i++) {
    started++; curUnit = i;
    const va = mod.HEAPU32[(base + i * 16) >>> 2];   // strict と同じく units は起動時の 1 度だけ読む. proc の下位 32bit = VA
    snap.set(mod.HEAPU8.subarray(0, img.length));
    const hOn = heapSet !== null && heapSet.has(i);
    if (hOn) { const L = mod.HEAPU8.length; if (!hbuf || hbuf.length < L) hbuf = new Uint8Array(L); hbuf.set(mod.HEAPU8); hLen = L; }
    const peekHit = peekUnits !== null && peekUnits.has(i);
    if (peekHit) console.error('[peek] unit ' + i + ' before: ' + peekAddrs.map((a) => a + '=' + mod.HEAPU32[a >>> 2]).join(' '));
    mod._m11_va_unit_begin();
    const oom0 = Number(mod._m11_va_oom()), vaUsed0 = Number(mod._m11_va_used());
    const gm0 = Number(mod._m11_probe_count(0)), fm0 = Number(mod._m11_probe_count(1));
    let r = null, err = null;
    try { r = mod._m11_call_unit_at(base, i); } catch (e) { err = e; }
    if (err && process.env.M11_TOLERANT_STACK && process.env.M11_TOLERANT_STACK.split(',').includes(String(i))) console.error('[tolerant][stack] unit ' + i + ' va=0x' + va.toString(16) + ': ' + ((err && err.stack) || err));   // #3325: 計測用 (既定 off)
    mod.__emscripten_stack_restore(sp0);
    if (peekHit) console.error('[peek] unit ' + i + ' after: ' + peekAddrs.map((a) => a + '=' + mod.HEAPU32[a >>> 2]).join(' ') + ' kind=' + (err ? (err.m11_dllmain_done !== undefined ? 'halt0' : 'err') : r));
    const oom = Number(mod._m11_va_oom()) > oom0;
    const clob = !intact();
    if (clob) clobber++;
    let kind, raw = null, msg = null, frame = null;
    if (err) {
      if (err.m11_dllmain_done !== undefined) raw = 'halt0';
      else {
        msg = String((err && err.message) || err).split('\n')[0];
        raw = /out of bounds/.test(msg) ? 'oob' : /unreachable/.test(msg) ? 'unreachable' : /abort/i.test(msg) ? 'abort' : 'other';
        frame = ((err.stack && /wasm-function\[(\d+)\]/.exec(err.stack)) || [])[1] ?? null;
      }
      kind = oom ? 'oom' : raw;
    } else if (r === 2) kind = 'miss';
    else if (r === 0) kind = 'noproc';
    else { kind = 'ok'; if (oom) okWithOom++; }
    if (clob && !SKIP.has(kind)) kind = 'clobber';   // ok/noproc でも InitTable を壊したら skip. 種類別の和と skipped を合わせる (m1)
    const vaHex = '0x' + va.toString(16);
    const vaBytes = Number(mod._m11_va_used()) - vaUsed0, gmD = Number(mod._m11_probe_count(0)) - gm0, fmD = Number(mod._m11_probe_count(1)) - fm0;
    if (SKIP.has(kind)) skipped.push({ i, va: vaHex, kind, raw, msg, frame, clobber: clob, va_bytes: vaBytes, getmem: gmD, freemem: fmD, oom, img_ranges: diffRanges() });
    kinds[kind] = (kinds[kind] || 0) + 1;
    if (hOn) heapRec.push({ i, va: vaHex, kind, ranges: heapDiff() });
    units.push([i, vaHex, kind, vaBytes, gmD, fmD, oom ? 1 : 0, clob ? 1 : 0]);
  }
};
let rc, threw = null, dllmainDone = false;
try { rc = mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) { rc = BigInt(e.m11_dllmain_done); dllmainDone = true; }
  else threw = (e && e.message) || String(e);
}
const ptrcheck = ptrCheck(mod, ptrPreSet);
const num = (f) => { try { return Number(f()); } catch (_) { return null; } };
const sk = skipped.map((s) => s.i);
if (process.env.M11_TOLERANT_OUT) fs.writeFileSync(process.env.M11_TOLERANT_OUT, JSON.stringify({ units, skipped }));
console.log('M11_TOLERANT ' + JSON.stringify({
  ptrcheck, hook_ran: hookRan, units_total: num(() => mod._m11_units_total()), attempted: started,
  ok: kinds.ok || 0, noproc: kinds.noproc || 0, miss: kinds.miss || 0,
  skipped: skipped.length, skipped_kinds: Object.fromEntries(Object.entries(kinds).filter(([k]) => SKIP.has(k))),
  kinds, clobber, ok_with_oom: okWithOom, skipped_units: sk.slice(0, 80),
  boot_rc: rc === undefined ? null : String(rc), threw, dllmain_done: dllmainDone,
  longjmp_hit: num(() => mod._m11_longjmp_hit()), getmem: num(() => mod._m11_probe_count(0)), freemem: num(() => mod._m11_probe_count(1)),
  va_calls: num(() => mod._m11_va_calls()), va_mb: Number((num(() => mod._m11_va_used()) || 0) / 1e6).toFixed(1),
  va_oom: num(() => mod._m11_va_oom()), icall_ok: num(() => mod._m11_icall_ok()), icall_miss: num(() => mod._m11_icall_miss()),
  icall_miss_uniq: num(() => mod._m11_icall_miss_uniq()), va_unit_budget_mb: Number(process.env.M11_VA_UNIT_BUDGET_MB ?? '256'),
  stub_uniq: num(() => mod._m11_stub_uniq()), stub_total: num(() => mod._m11_stub_total()),
}));
if (heapSet) {
  const p1 = new Map(JSON.parse(fs.readFileSync(heapFrom, 'utf8')).skipped.map((s) => [s.i, s.kind]));
  const match = heapRec.length === heapSet.size && heapRec.every((r) => p1.get(r.i) === r.kind);
  const out = { from: heapFrom, img_len: img.length, layout: LAY, match, units: heapRec };
  if (process.env.M11_HEAP_OUT) fs.writeFileSync(process.env.M11_HEAP_OUT, JSON.stringify(out));
  console.log('M11_TOLERANT_HEAP ' + JSON.stringify({ n: heapRec.length, match, layout: LAY, img_len: img.length }));
}
