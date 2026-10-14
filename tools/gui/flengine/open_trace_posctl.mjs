// WIN-13 (#2905): open 系 trace の正の対照。存在しないパスの CreateFileW を wasm 上で 1 回呼び、
// shim/src/file.c の SHIMOPEN 行 (path・成否・errno) が出ることを確認する。PASS = 1 行・ok=false・err=2 (ENOENT → ERROR_FILE_NOT_FOUND)。
//   node open_trace_posctl.mjs [--wasm path.cjs]
import path from 'path';
import { fileURLToPath } from 'url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const wi = args.indexOf('--wasm');
const wasmCjs = path.resolve(wi >= 0 ? args[wi + 1] : path.resolve(HERE, '../work/flengine/m11_gui.cjs'));
const errs = [];
const m2 = await import(wasmCjs);
const mod = await m2.default({ printErr: (s) => { errs.push(String(s)); } });
const p = 'C:\\nonexistent\\x.txt';
const buf = mod._malloc(2 * (p.length + 1));
for (let i = 0; i < p.length; i++) { mod.HEAPU8[buf + 2 * i] = p.charCodeAt(i) & 0xff; mod.HEAPU8[buf + 2 * i + 1] = p.charCodeAt(i) >> 8; }
mod.HEAPU8[buf + 2 * p.length] = 0; mod.HEAPU8[buf + 2 * p.length + 1] = 0;
const h = mod._CreateFileW(buf, 0x80000000, 0, 0, 3, 0, 0);
const lines = errs.filter((s) => s.startsWith('SHIMOPEN '));
const o = lines.length === 1 ? JSON.parse(lines[0].slice(9)) : null;
const pass = o !== null && o.path === p && o.ok === false && o.err === 2 && o.w === false;
console.log(JSON.stringify({ ret: h, n_shimopen: lines.length, record: o, pass }));
process.exit(pass ? 0 : 1);
