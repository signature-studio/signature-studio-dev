// GUI-3 (#174): 指向プローブ。自然起動 (DllMain attach, 22 unit) では RegisterClass*/CreateWindowEx* に届かないため、
//   実 FLEngine の lift 済みコードを JS から直接呼んで「実 WNDCLASS (PE の .data 実値) → shim → m11_icall(WNDPROC)」の経路を確認する。
//   自然到達ではない (呼出元が JS)。到達点の主張は run.mjs (自然起動 / survey) と分けて扱う。
//   node probe.mjs [--wasm path.cjs] [--out probe.json]
import fs from 'fs';
import path from 'path';
const HERE = path.dirname(new URL(import.meta.url).pathname);
const M11 = process.env.GF_M11 || path.resolve(HERE, '../../m11');
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const wasmCjs = path.resolve(opt('--wasm', path.resolve(HERE, '../work/flengine/m11_gui.cjs')));
const errs = [];
const m2 = await import(wasmCjs);
const mod = await m2.default({ printErr: (s) => { errs.push(String(s)); } });
mod.HEAPU8.set(fs.readFileSync(M11 + '/work/m11_image.bin'), 0);
const sp = mod._emscripten_stack_get_current();
let bootOk = false;
try { mod._m11_boot_enter(0n, 1n); } catch (e) { bootOk = !!(e && e.m11_dllmain_done !== undefined); }
mod.__emscripten_stack_restore(sp);
const dv = () => new DataView(mod.HEAPU8.buffer);
const u64 = (a) => dv().getBigUint64(a, true);
const u16s = (a) => { let s = ''; for (let i = 0; i < 80; i++) { const c = dv().getUint16(a + 2 * i, true); if (!c) break; s += String.fromCharCode(c); } return s; };
const inst = Number(u64(18793112) & 0xffffffffn);   // HInstance (function_52a7f0 が [0x11e1798] から読む値)

// PE の .data に静的実体がある実 WNDCLASS (function_71dd80 / function_867e10 / function_52a7f0 が RegisterClassW に渡す定数)
const CLASSES = [
  { site: 'function_71dd80', wc: 16736032 },
  { site: 'function_867e10', wc: 16817336 },
];
const out = { boot_dllmain_done: bootOk, hinstance: inst, classes: [], util_window: null, windows: [] };
const catchRun = (f) => { const sp0 = mod._emscripten_stack_get_current(); try { return { ok: true, v: f() }; } catch (e) { mod.__emscripten_stack_restore(sp0); return { ok: false, err: ((e && e.message) || String(e)).split('\n')[0], failfast: e && e.gui_failfast }; } };
for (const c of CLASSES) {
  const nameP = Number(u64(c.wc + 64)), wndproc = Number(u64(c.wc + 8));
  const name = u16s(nameP);
  const r = catchRun(() => mod._function_425260(c.wc));   // = RegisterClassW の lift 済みラッパ (ptr 引数のみ)
  out.classes.push({ site: c.site, wndclass_va: '0x' + c.wc.toString(16), name, lpfnWndProc: '0x' + wndproc.toString(16), atom: r.ok ? Number(r.v) : null, err: r.err || null });
  const miss0 = mod._m11_icall_miss(), icall0 = mod._gf_icall_count();
  const w = catchRun(() => mod._CreateWindowExW(0, nameP, 0, 0x80000000 | 0, 0, 0, 64, 48, 0, 0, inst, 0));
  const h = w.ok ? Number(w.v) >>> 0 : null;
  out.windows.push({ name, hwnd: h === null ? null : '0x' + h.toString(16), hwnd_below_2_31: h !== null && h !== 0 ? h < 0x80000000 : null, err: w.err || null,
    wndproc_icall_calls: mod._gf_icall_count() - icall0, thunk_calls: mod._gf_thunk_count(), m11_icall_miss_delta: mod._m11_icall_miss() - miss0 });
}
// AllocateHWnd 相当 (function_52a7f0): GetClassInfoW → RegisterClassW → CreateWindowExW → SetWindowLongPtrW(GWLP_WNDPROC)
const calls0 = {};
const r52 = catchRun(() => mod._function_52a7f0(0n));
out.util_window = { fn: 'function_52a7f0', ret: r52.ok ? '0x' + BigInt.asUintN(64, r52.v).toString(16) : null, err: r52.err || null };
// ABI 確認 (INTEGRATION.md §4): shim の共有領域は GLOBAL_BASE 以降 (>= 0x10000)、発行ハンドルは 31bit 内
const dc = catchRun(() => mod._GetDC(0));
out.abi = { gui_shared_ptr: mod._gui_shared_ptr(), gui_shared_ptr_ge_0x10000: mod._gui_shared_ptr() >= 0x10000,
  screen_dc: dc.ok ? '0x' + (Number(dc.v) >>> 0).toString(16) : null, screen_dc_in_31bit: dc.ok && Number(dc.v) > 0 && Number(dc.v) < 0x80000000 };
if (dc.ok) catchRun(() => mod._ReleaseDC(0, dc.v));
mod._gui_reach_dump();
out.reach = [];
for (const l of errs) { const m = /GUI-REACH (\d+) (\w+) (\d+) (IMPL|STUB) P(\S+)$/.exec(l); if (m) out.reach.push({ order: +m[1], name: m[2], calls: +m[3], kind: m[4], prio: m[5] }); }
out.icall_miss = mod._m11_icall_miss();
const json = JSON.stringify(out);
const of = opt('--out', null);
if (of) fs.writeFileSync(of, JSON.stringify(out, null, 1));
console.log('FLGUI_PROBE ' + json);
process.exit(0);
