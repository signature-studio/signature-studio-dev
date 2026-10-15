// #3478: DllMain attach (m11_boot_enter) の InitUnits がどの unit で止まるかを unit 単位の trace で記録する。
//   node boot_halt_probe.mjs --wasm <m11_gui*.cjs> [--out result.json]
//   関数名 (Halt0 までの呼出し鎖) は -g2 の診断 build で出る (cfi_boot7.sh と同じ sed 複製)。-g1 の build でも停止 unit は出る。
// 出力 (JSON): units_total / units_run / init_count / icall_miss、最後に開始した unit (0 起算)、
//   unit VA (trace の値 + 0x400000 = arr1 の値)、Halt0 (m11_dllmain_done の JS 例外) の有無と呼出し鎖。
//   halt_mem: 停止後の読取り。番地は wasm 線形メモリ上の値 (LVA = VA - 0x400000)。obj = [0x11f7110] (VA 0x15f7110)、
//     obj の vtable・vtable[0]・vtable[0] の先頭 8 バイトと jmp 先 (e9 rel32)・jmp 先の先頭 16 バイト、
//     第 3 引数 (VA 0x8494fc = wasm 0x4494fc) の 16 バイト。
// 判定は出力 JSON で行う (常に exit 0)。
import fs from 'fs';
import path from 'path';
Error.stackTraceLimit = 400;
const HERE = path.dirname(new URL(import.meta.url).pathname);
const M11 = process.env.GF_M11 || path.resolve(HERE, '../../m11');
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const wasmCjs = path.resolve(opt('--wasm', path.resolve(HERE, '../work/flengine/m11_gui.cjs')));
const outFile = opt('--out', null);

const errs = [];
const m2 = await import(wasmCjs);
const mod = await (m2.default ? m2.default({ printErr: (s) => { errs.push(String(s)); } }) : m2());
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
mod._m11_set_trace(1);
let halt = null, threw = null;
try { mod._m11_boot_enter(0n, 1n); } catch (e) {
  if (e && e.m11_dllmain_done !== undefined) halt = String(e.stack || '').split('\n').slice(1);
  else threw = String((e && e.message) || e);
}
let last = null;
for (const l of errs) { const m = /\[m11\]\[unit (\d+)\/(\d+)\] init=0x([0-9a-f]+)/.exec(l); if (m) last = m; }
const frameName = (l) => l.trim().replace(/^at /, '').split(' (')[0].split('.').pop();
const chain = halt ? halt.map(frameName).filter((n) => /^(function_|_?m11_|tr_)/.test(n)) : [];
const u32 = (a) => (a >= 0 && a + 4 <= mod.HEAPU8.length ? mod.HEAPU32[a >>> 2] : null);
const hex32 = (n) => (n === null ? null : '0x' + (n >>> 0).toString(16));
const hexBytes = (a, n) => Array.from(mod.HEAPU8.subarray(a, a + n), (b) => b.toString(16).padStart(2, '0')).join(' ');
const VA_BASE = 0x400000, ARG3_VA = 0x8494fc;
const objP = u32(0x11f7110), vtP = objP ? u32(objP) : null, vt0 = vtP ? u32(vtP) : null;
const i32u = (a) => new DataView(mod.HEAPU8.buffer).getInt32(a, true);
const vt0Jmp = vt0 !== null && mod.HEAPU8[vt0 + 4] === 0xe9 ? vt0 + 9 + i32u(vt0 + 5) : null;
const halt_mem = {
  obj: hex32(objP), vtable: hex32(vtP), vtable0: hex32(vt0),
  vtable0_bytes: vt0 ? hexBytes(vt0, 8) : null,
  vtable0_jmp_target: hex32(vt0Jmp), vtable0_jmp_bytes: vt0Jmp ? hexBytes(vt0Jmp, 16) : null,
  arg3_va: '0x' + ARG3_VA.toString(16), arg3_wasm: '0x' + (ARG3_VA - VA_BASE).toString(16), arg3_bytes: hexBytes(ARG3_VA - VA_BASE, 16),
};
const result = {
  units_total: mod._m11_units_total(), units_run: mod._m11_units_run(), init_count: mod._m11_init_count(),
  icall_miss: mod._m11_icall_miss(), longjmp_halt0: halt !== null, threw,
  last_unit: last ? { index0: Number(last[1]) - 1, total: Number(last[2]), unit_va: '0x' + (0x400000 + parseInt(last[3], 16)).toString(16) } : null,
  halt_chain: chain, halt_mem,
};
const json = JSON.stringify(result);
if (outFile) fs.writeFileSync(outFile, JSON.stringify(result, null, 1));
console.log('BOOT_HALT ' + json);
process.exit(0);
