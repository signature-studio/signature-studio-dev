// unit 1..idx を順に実行し、unit idx+1 の shimx 呼出しごとに「呼出し直前の GetLastError」と「呼出し元の wasm スタック」を出す (SHX-T9k #2593)。
//   node probe_sxlasterr_2593.mjs <m11_sx_trace_*.cjs 絶対パス> [idx 既定 21 (= unit 22 を trace)]
// 出力: [sxt] 行 (呼出し順・le=呼出し直前の GetLastError・名前) と、各呼出しの wasm スタック上位フレーム (wasm-function[n]:0xOFF)。
// 注意: 0x11e3af0 等は LVA (VA - 0x400000)。sxt_set_print / sxt_set_stack は trace ビルドのみ。
import fs from 'fs';
const cjs = process.argv[2];
const idx = Number(process.argv[3] ?? 21);
const M11 = new URL('../', import.meta.url).pathname;
Error.stackTraceLimit = 40;
const m2 = await import(cjs);
const image = fs.readFileSync(M11 + 'work/m11_image.bin');
const errs = [];
const mod = await (m2.default || m2)({ printErr: (s) => { errs.push(String(s)); } });
mod.HEAPU8.set(image, 0);
mod._m11_set_survey(1);
const sp = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) throw e; mod.__emscripten_stack_restore(sp); }
const sp0 = mod._emscripten_stack_get_current();
const run = (i) => {
  try { return 'ret=' + mod._m11_call_unit(i); }
  catch (e) {
    try { mod.__emscripten_stack_restore(sp0); } catch (_) {}
    return 'exc=' + (e && e.m11_dllmain_done !== undefined ? 'halt0' : String((e && e.message) || e).split('\n')[0]);
  }
};
for (let i = 0; i < idx; i++) run(i);
mod._m11_set_trace(1); if (mod._shimx_set_trace) mod._shimx_set_trace(1);
mod._sxt_set_print(1); mod._sxt_set_stack(1);
const e0 = errs.length;
const r = run(idx);
console.log(`unit ${idx + 1} (trace) ${r} lasterr=${mod._GetLastError()}`);
for (const l of errs.slice(e0)) if (l.startsWith('[sxt]')) console.log(l);
const st = globalThis.sxt_stk || [];
console.log(`sxt_stk records=${st.length}`);
st.forEach(([i, le, s], k) => {
  const fr = String(s).split('\n').slice(1, 6).map((x) => x.trim()).join(' | ');
  console.log(`#${k} idx=${i} le=${le} ${fr}`);
});
const readW = (p) => { let s = ''; const u = new Uint16Array(mod.HEAPU8.buffer, p, 260); for (let j = 0; j < 260 && u[j]; j++) s += String.fromCharCode(u[j]); return s; };
const nret = mod._sxt_ret_n();
for (let k = 0; k < nret; k++) {
  if (mod._sxt_ret_unit(k) !== idx + 1) continue;
  const i = mod._sxt_ret_idx(k);
  const name = mod.UTF8ToString(mod._sxt_name(i));
  const a = BigInt(mod._sxt_ret_a(k)), b = BigInt(mod._sxt_ret_b(k)), r = BigInt(mod._sxt_ret_r(k));
  const hx = (x) => '0x' + x.toString(16);
  if (name === 'GetModuleHandleW') console.log(`ret ${name} lpModuleName=${hx(a)} "${readW(Number(a))}" -> ${hx(r)}`);
  else if (name === 'GetProcAddress') {
    const pn = b < 0x10000n ? `ord ${b}` : `"${mod.UTF8ToString(Number(b))}"`;
    console.log(`ret ${name} hModule=${hx(a)} proc=${pn} -> ${hx(r)}`);
  } else console.log(`ret ${name} a=${hx(a)} b=${hx(b)} -> ${hx(r)}`);
}
