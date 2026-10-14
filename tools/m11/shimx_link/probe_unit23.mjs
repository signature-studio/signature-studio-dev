// unit 23 (index 22) の icall miss・slot (0x15f10e0)・GetProcAddress 呼出し数を、前処理 unit 1..idx-1 の後で 1 回実測する probe (SHX-T9e #1607).
//   node probe_unit23.mjs <m11_sx_*.cjs | m11_boot.cjs> <unit_index (0 始まり, 既定 22)>
//   素材: tools/m11/work/ (work-m11) と tools/m11/work/shimx_link/m11_sx_trace_soft_fix.cjs (build.sh --trace --soft --fix)
import fs from 'fs';
import path from 'path';

const M11 = path.resolve(new URL('../', import.meta.url).pathname);
const cjs = path.resolve(process.argv[2]);
const idx = Number(process.argv[3] ?? 22);
const m2 = await import(cjs);
const image = fs.readFileSync(M11 + '/work/m11_image.bin');
const errs = [];
const mod = await (m2.default || m2)({ printErr: (s) => { errs.push(String(s)); } });
mod.HEAPU8.set(image, 0);
mod._m11_set_survey(1);
if (process.env.SHIMX_TRACE === '1' && mod._shimx_set_trace) mod._shimx_set_trace(1);
const sp = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) throw e; mod.__emscripten_stack_restore(sp); }
const sp0 = mod._emscripten_stack_get_current();
// survey_trace.mjs と同じく、対象 unit の前の unit 0..idx-1 を先に順に実行する (状態を揃えるため)
const slotPre = () => { const dv = new DataView(mod.HEAPU8.buffer); return dv.getBigUint64(0x15f10e0, true); };
const pre = (typeof mod._sxt_n === 'function') ? mod._sxt_n() : 0;
const gpIdx = []; for (let i = 0; i < pre; i++) { const nm = mod.UTF8ToString(mod._sxt_name(i)); if (nm === 'GetProcAddress' || nm === 'GetModuleHandleW') gpIdx.push([nm, i]); }
const gpc = () => gpIdx.map(([nm, i]) => nm + '=' + mod._sxt_count(i)).join(' ');
for (let i = 0; i < idx; i++) {
  const s0 = slotPre();
  try { mod._m11_call_unit(i); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) { try { mod.__emscripten_stack_restore(sp0); } catch (_) {} } }
  const s1 = slotPre();
  if (s0 !== s1 || i >= idx - 3) console.log('PRE|unit', i + 1, 'slot', '0x' + s1.toString(16), 'gp', gpc());
}
// .bss slot 0x15f10e0 (LVA = RVA, M11_LB_BASE=0)。0 なら fallback 0x457860 に流れる
const slotVal = () => { const dv = new DataView(mod.HEAPU8.buffer); return Number(dv.getBigUint64(0x15f10e0, true)).toString(16); };
console.log('SLOT_BEFORE_UNIT|0x' + slotVal());
const e0 = errs.length;
const HAS = typeof mod._sxt_n === 'function';
const nn = HAS ? mod._sxt_n() : 0;
const names = []; for (let i = 0; i < nn; i++) names.push(mod.UTF8ToString(mod._sxt_name(i)));
const c0 = []; for (let i = 0; i < nn; i++) c0.push(mod._sxt_count(i));
console.log('unit', idx + 1, 'lva', '0x' + mod._m11_unit_va(idx).toString(16));
console.log('SLOT_AT_UNIT|0x' + slotVal());
let res;
try { res = 'ret=' + mod._m11_call_unit(idx); }
catch (e) { res = 'exc=' + (e && e.m11_dllmain_done !== undefined ? 'halt0' : String((e && e.message) || e).split('\n')[0]); }
console.log(res);
for (let i = 0; i < nn; i++) { const d = mod._sxt_count(i) - c0[i]; if (d) console.log('CALL|' + names[i] + '=' + d); }
if (!HAS) console.log('(sxt 無し: 既存 M11 ビルド)');
console.log('MISS_UNIQ', mod._m11_icall_miss_uniq(), 'MISS_TOTAL', mod._m11_icall_miss());
for (let k = 0; k < mod._m11_icall_miss_uniq(); k++) console.log('MISS_AT|' + k + ' ' + mod._m11_icall_miss_at(k).toString(16));
// 戻り値ログ (trace_rt.c の sxt_ret): 全 unit 分を出し、unit idx+1 の行を後で見る
if (typeof mod._sxt_ret_n === 'function') {
  const rn = mod._sxt_ret_n();
  for (let k = 0; k < rn; k++) {
    const nm = mod.UTF8ToString(mod._sxt_name(mod._sxt_ret_idx(k)));
    const a = mod._sxt_ret_a(k), b = mod._sxt_ret_b(k);
    const u8 = mod.HEAPU8;
    let str = '';
    if (nm === 'GetModuleHandleW' && a > 0 && a < u8.length) { for (let p = a; p + 1 < u8.length && (u8[p] | u8[p + 1] << 8); p += 2) str += String.fromCharCode(u8[p] | u8[p + 1] << 8); }
    if (nm === 'GetProcAddress' && b > 0 && b < u8.length) { for (let p = b; p < u8.length && u8[p]; p++) str += String.fromCharCode(u8[p]); }
    console.log('RET|unit', mod._sxt_ret_unit(k), nm, 'a=0x' + a.toString(16), 'b=0x' + b.toString(16), 'r=0x' + mod._sxt_ret_r(k).toString(16), str ? 'name=' + JSON.stringify(str) : '');
  }
}
for (const l of errs.slice(e0)) console.log('ERR|' + l.slice(0, 300));
