// SHX-T9g (#1986): survey_trace.mjs と同じ unit 隔離実行で、oob / halt0 の unit に wasm trap frame (関数 index・バイトオフセット付き) を残す。
//   node survey_frames.mjs <m11_*.cjs> [--out DIR] [--only 23,55,...]
// 出力: <DIR>/<tag>.frames.json (unit ごとの kind と frames)。frames は wasm-function[N]+offset の生 frame。
// 関数名は wasm の export 名だけで解決する (内部関数は index のまま残す)。
import fs from 'fs';
import path from 'path';

Error.stackTraceLimit = 60;
const M11 = path.resolve(new URL('../', import.meta.url).pathname);
const cjs = path.resolve(process.argv[2]);
const outDir = process.argv.includes('--out') ? process.argv[process.argv.indexOf('--out') + 1] : path.dirname(cjs);
const only = process.argv.includes('--only') ? process.argv[process.argv.indexOf('--only') + 1].split(',').map(Number) : null;
const tag = path.basename(cjs).replace(/\.cjs$/, '');
const m2 = await import(cjs);
const image = fs.readFileSync(M11 + '/work/m11_image.bin');
const N = 942;
const wasmBin = fs.readFileSync(cjs + '.wasm');
const fnNames = new Map();
{
  let pos = 8;
  const leb = () => { let r = 0, s = 0, x; do { x = wasmBin[pos++]; r |= (x & 0x7f) << s; s += 7; } while (x & 0x80); return r >>> 0; };
  while (pos < wasmBin.length) {
    const id = wasmBin[pos++]; const sz = leb(); const end = pos + sz;
    if (id === 7) { const n = leb(); for (let k = 0; k < n; k++) { const l = leb(); const nm = wasmBin.toString('utf8', pos, pos + l); pos += l; const kind = wasmBin[pos++]; const idx = leb(); if (kind === 0 && !fnNames.has(idx)) fnNames.set(idx, nm); } }
    pos = end;
  }
}
const resolve = (l) => { const m = /wasm-function\[(\d+)\]:(0x[0-9a-f]+)/.exec(l); if (!m) return l.trim(); const i = +m[1]; return (fnNames.get(i) || 'f' + i) + '@' + m[2]; };
let errs = [];
async function boot() {
  errs = [];
  const mod = await (m2.default || m2)({ printErr: (s) => { errs.push(String(s)); if (errs.length > 400) errs.shift(); } });
  mod.HEAPU8.set(image, 0);
  mod._m11_set_survey(1);
  if (process.env.SHIMX_TRACE === '1' && mod._shimx_set_trace) mod._shimx_set_trace(1);
  const sp = mod._emscripten_stack_get_current();
  try { mod._m11_boot_enter(0n, 1n); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) throw e; mod.__emscripten_stack_restore(sp); }
  return mod;
}
let mod = await boot();
let sp0 = mod._emscripten_stack_get_current();
const unitVa0 = [mod._m11_unit_va(0), mod._m11_unit_va(N - 1)];
const tableIntact = () => mod._m11_unit_va(0) === unitVa0[0] && mod._m11_unit_va(N - 1) === unitVa0[1];
const out = [];
const iso = process.argv.includes('--iso');   // 各 unit を毎回新インスタンスで単独実行 (前 unit の状態を持ち越さない)
for (let i = 0; i < N; i++) {
  if (iso && (!only || only.includes(i + 1))) { mod = await boot(); sp0 = mod._emscripten_stack_get_current(); unitVa0.length = 0; unitVa0.push(mod._m11_unit_va(0), mod._m11_unit_va(N - 1)); }
  if (only && !only.includes(i + 1)) continue;
  const e0 = errs.length;
  let kind = 'ok', frames = null, detail = null;
  try {
    const r = mod._m11_call_unit(i);
    kind = r === 1 ? 'ok' : r === 0 ? 'noproc' : r === 2 ? 'closure_outside' : 'range';
  } catch (e) {
    if (e && e.m11_dllmain_done !== undefined) { kind = 'halt0'; }
    else {
      const msg = ((e && e.message) || String(e)).split('\n')[0];
      kind = /Aborted|already aborted/.test(msg) ? 'abort' : /out of bounds/.test(msg) ? 'oob' : /unreachable/.test(msg) ? 'unreachable' : 'trap';
      detail = msg;
    }
    frames = ((e && e.stack) || '').split('\n').filter((l) => /wasm-function|^\s*at /.test(l)).slice(0, 40).map(resolve);
  }
  if (!tableIntact()) kind = 'clobber';
  const msgs = errs.slice(e0).filter((l) => /MessageBox|\[shimx\]|FAIL-FAST/.test(l)).slice(0, 3);
  if (!only || only.includes(i + 1)) out.push({ unit: i + 1, lva: '0x' + mod._m11_unit_va(i).toString(16), kind, detail, frames, ...(msgs.length ? { msgs } : {}) });
  if (kind === 'abort' || kind === 'clobber') { mod = await boot(); sp0 = mod._emscripten_stack_get_current(); }
  else if (kind !== 'ok' && kind !== 'noproc' && kind !== 'closure_outside') { try { mod.__emscripten_stack_restore(sp0); } catch (_) {} }
}
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, tag + '.frames.json'), JSON.stringify(out, null, 1));
const k = {}; for (const r of out) k[r.kind] = (k[r.kind] || 0) + 1;
console.log('SXF_FRAMES ' + JSON.stringify(k));
