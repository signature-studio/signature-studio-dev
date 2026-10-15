// WIN-4 (#2715): CreateFruityInstance (0x1375990) の呼出しプローブ。
//   DllMain attach (寛容起動) の後、glue 経由で CreateFruityInstance(0xC0, 0xEDE95A, host, &iface) を呼ぶ。
//   THostInstance (0x38 B) は STARTUP.md §0 の layout (+0 vtable, +8=1, +0xc=flags, +0x18="FL Studio", +0x30=cmdline バッファ) で wasm メモリに作る。
//   署名検証 (S14) は shim の WinVerifyTrust=0 / CertGetNameStringW="Image Line NV" で通す (shim 側の既存実装)。
//   node cfi_probe.mjs [--wasm path.cjs] [--out cfi.json] [--flags 0] [--trace-out open_trace.jsonl]
//   open_trace: CreateFileW の呼出し (WIN-13 #2905・shim/src/file.c の SHIMOPEN 行) を assettrace の trace 形式 v1 で保存する
import fs from 'fs';
import path from 'path';
const HERE = path.dirname(new URL(import.meta.url).pathname);
const M11 = process.env.GF_M11 || path.resolve(HERE, '../../m11');
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const wasmCjs = path.resolve(opt('--wasm', path.resolve(HERE, '../work/flengine/m11_gui.cjs')));
const flags = Number(opt('--flags', '0'));
const errs = [];
const m2 = await import(wasmCjs);
const mod = await m2.default({ printErr: (s) => { errs.push(String(s)); } });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
const out = { wasm: path.basename(wasmCjs), boot: null, host: null, call: null, reach: [], errs_tail: [] };
const sp0 = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); out.boot = { ok: true }; }
catch (e) { out.boot = { ok: !!(e && e.m11_dllmain_done !== undefined), err: ((e && e.message) || String(e)).split('\n')[0] }; }
mod.__emscripten_stack_restore(sp0);
const dv = () => new DataView(mod.HEAPU8.buffer);
// THostInstance: vtable (dummy, 0x40 B) / version=1 / flags / parent hwnd=0 / "FL Studio" (ANSI, NUL) / cmdline buffer 0x8000 B
const vt = mod._malloc(0x40), name = mod._malloc(16), cmd = mod._malloc(0x8000), host = mod._malloc(0x38), iface = mod._malloc(8);
mod.HEAPU8.fill(0, vt, vt + 0x40); mod.HEAPU8.fill(0, cmd, cmd + 0x8000);
mod.HEAPU8.set(new TextEncoder().encode('FL Studio\0'), name);
mod.HEAPU8.fill(0, host, host + 0x38); mod.HEAPU8.fill(0, iface, iface + 8);
dv().setBigUint64(host + 0x00, BigInt(vt), true);
dv().setUint32(host + 0x08, 1, true);
dv().setUint32(host + 0x0c, flags >>> 0, true);
dv().setBigUint64(host + 0x18, BigInt(name), true);
dv().setBigUint64(host + 0x30, BigInt(cmd), true);
out.host = { ptr: '0x' + host.toString(16), version: 1, flags, name_ptr: '0x' + name.toString(16), cmd_ptr: '0x' + cmd.toString(16), iface_out: '0x' + iface.toString(16) };
const sp1 = mod._emscripten_stack_get_current();
const t0 = Date.now();
try {
  const r = mod._CreateFruityInstance(0xC0n, 0xEDE95An, BigInt(host), BigInt(iface));
  out.call = { returned: true, ret: Number(BigInt.asIntN(64, r)), ms: Date.now() - t0 };
} catch (e) {
  mod.__emscripten_stack_restore(sp1);
  out.call = { returned: false, err: ((e && e.message) || String(e)).split('\n')[0], failfast: !!(e && e.gui_failfast), ms: Date.now() - t0 };
}
out.iface = '0x' + dv().getBigUint64(iface, true).toString(16);
mod._gui_reach_dump();
for (const l of errs) { const m = /GUI-REACH (\d+) (\w+) (\d+) (IMPL|STUB) P(\S+)$/.exec(l); if (m) out.reach.push({ order: +m[1], name: m[2], calls: +m[3], kind: m[4], prio: m[5] }); }
out.open_trace = errs.filter((s) => s.startsWith('SHIMOPEN ')).map((s) => JSON.parse(s.slice(9)));
const tr = opt('--trace-out', null);
if (tr) fs.writeFileSync(tr, out.open_trace.map((o) => JSON.stringify(o)).join('\n') + (out.open_trace.length ? '\n' : ''));
out.errs_n = errs.length;
out.errs_tail = errs.slice(-12).map((s) => s.slice(0, 200));
out.icall_miss = mod._m11_icall_miss();
out.icall_miss_targets = Array.from({ length: Math.min(mod._m11_icall_miss_uniq(), 32) }, (_, i) => '0x' + (mod._m11_icall_miss_at(i) >>> 0).toString(16));
const of = opt('--out', null);
const json = JSON.stringify(out, null, 1);
if (of) fs.writeFileSync(of, json);
console.log(json);
