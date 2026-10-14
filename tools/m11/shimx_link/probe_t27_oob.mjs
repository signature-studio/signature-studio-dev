// #1630 SHX-T27: trap 時点の wasm 影スタックを読み、function_4133f0 (UStrAsg 相当) の dest/src/old を採る。
//   node probe_t27_oob.mjs <m11_sx_trace_soft.cjs>
// function_4133f0 は -O0 のため引数と中間値が影スタック (frame 80 bytes, trap 時 sp = fp) に残る:
//   fp+72=arg1(dest) fp+64=arg2(src) fp+56=src 退避 fp+40=old(=*dest) fp+32=old-16
import fs from 'fs';
import path from 'path';

const M11 = path.resolve(new URL('../', import.meta.url).pathname);
const cjs = path.resolve(process.argv[2]);
const m2 = await import(cjs);
const mod = await (m2.default || m2)({ printErr: () => {} });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
let threw = null;
try { mod._m11_boot_enter(0n, 1n); } catch (e) { threw = String(e && e.message || e); }
const sp = mod._emscripten_stack_get_current();
const h = () => new DataView(mod.HEAPU8.buffer);
const u64 = (a) => h().getBigUint64(a, true);
const u32 = (a) => h().getUint32(a, true);
const hex = (v) => '0x' + BigInt(v).toString(16);
console.log(JSON.stringify({ threw, sp: hex(sp), mem_bytes: hex(mod.HEAPU8.length) }));
const fr = { dest: u64(sp + 72), src: u64(sp + 64), src_saved: u64(sp + 56), old: u64(sp + 40), hdr: u64(sp + 32) };
console.log(Object.fromEntries(Object.entries(fr).map(([k, v]) => [k, hex(v)])));
// 呼出元 (function_446400) の frame を探す: sp+80 以降の 8 byte 値を 0x1000 byte 分ダンプ
if (process.argv.includes('--dump')) {
  for (let off = 80; off < 80 + 0x200; off += 8) console.log(hex(sp + off), hex(u64(sp + off)));
}
