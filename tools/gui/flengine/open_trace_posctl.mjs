// WIN-13 (#2905) / WIN-14 (#2964): open 系 trace の正の対照。存在しないパスの CreateFileW を wasm 上で呼び、
// shim/src/file.c の SHIMOPEN 行 (path・成否・errno) が出ることを確認する。
//   対照 1 (direct): JS から _CreateFileW を直接呼ぶ。lift 関数の外からの呼出しなので caller は空。
//   対照 2 (lifted): lift 済み関数 function_423230 (中で CreateFileW を呼ぶ) から同じパスを開く。caller は function_423230 (wasm function index の表で解決)。
// PASS = 両対照とも 1 行・ok=false・err=2 (ENOENT → ERROR_FILE_NOT_FOUND)・path 一致、かつ direct の caller は空・lifted の caller は function_423230。
//   node open_trace_posctl.mjs [--wasm path.cjs]
import path from 'path';
import { fileURLToPath } from 'url';
import { wasmFuncNames, fillCaller } from './wasm_fnnames.mjs';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const wi = args.indexOf('--wasm');
const wasmCjs = path.resolve(wi >= 0 ? args[wi + 1] : path.resolve(HERE, '../work/flengine/m11_gui.cjs'));
const names = wasmFuncNames(wasmCjs + '.wasm');
const errs = [];
const m2 = await import(wasmCjs);
const mod = await m2.default({ printErr: (s) => { errs.push(String(s)); } });
const p = 'C:\\nonexistent\\x.txt';
const buf = mod._malloc(2 * (p.length + 1));
for (let i = 0; i < p.length; i++) { mod.HEAPU8[buf + 2 * i] = p.charCodeAt(i) & 0xff; mod.HEAPU8[buf + 2 * i + 1] = p.charCodeAt(i) >> 8; }
mod.HEAPU8[buf + 2 * p.length] = 0; mod.HEAPU8[buf + 2 * p.length + 1] = 0;
const run = (call) => {
  errs.length = 0;
  const ret = call();
  const lines = errs.filter((s) => s.startsWith('SHIMOPEN '));
  const record = lines.length === 1 ? fillCaller(JSON.parse(lines[0].slice(9)), names) : null;
  const pass = record !== null && record.path === p && record.ok === false && record.err === 2 && record.w === false;
  return { ret, n_shimopen: lines.length, record, pass };
};
const direct = run(() => mod._CreateFileW(buf, 0x80000000, 0, 0, 3, 0, 0));
const lifted = run(() => mod._function_423230(buf, 0x80000000, 0, 0, 3, 0, 0));
const pass = direct.pass && direct.record.caller === '' && lifted.pass && lifted.record.caller === 'function_423230';
console.log(JSON.stringify({ direct, lifted, pass }));
process.exit(pass ? 0 : 1);
