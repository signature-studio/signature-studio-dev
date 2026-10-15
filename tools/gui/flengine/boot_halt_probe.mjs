// #3478: DllMain attach (m11_boot_enter) の InitUnits がどの unit で止まるかを unit 単位の trace で記録する。
//   node boot_halt_probe.mjs --wasm <m11_gui*.cjs> [--out result.json]
//   関数名 (Halt0 までの呼出し鎖) は -g2 の診断 build で出る (cfi_boot7.sh と同じ sed 複製)。-g1 の build でも停止 unit は出る。
// 出力 (JSON): units_total / units_run / init_count / icall_miss、最後に開始した unit (0 起算)、
//   unit VA (trace の値 + 0x400000 = arr1 の値)、Halt0 (m11_dllmain_done の JS 例外) の有無と呼出し鎖。
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
const result = {
  units_total: mod._m11_units_total(), units_run: mod._m11_units_run(), init_count: mod._m11_init_count(),
  icall_miss: mod._m11_icall_miss(), longjmp_halt0: halt !== null, threw,
  last_unit: last ? { index0: Number(last[1]) - 1, total: Number(last[2]), unit_va: '0x' + (0x400000 + parseInt(last[3], 16)).toString(16) } : null,
  halt_chain: chain,
};
const json = JSON.stringify(result);
if (outFile) fs.writeFileSync(outFile, JSON.stringify(result, null, 1));
console.log('BOOT_HALT ' + json);
process.exit(0);
