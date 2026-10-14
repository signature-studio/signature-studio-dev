// #1630 SHX-T27: survey_trace.mjs と同じ方式 (survey モード boot の後、unit 1..N を 1 本ずつ try/catch で順に実行) で、
// SHIMX_TRACE_FILE (shimx の file trace) の件数と api 内訳を採る。
//   node probe_t27_ftrace.mjs <m11_sx_trace_*.cjs> <N: 最後に実行する unit 番号 (1 始まり)> [--out DIR]
// 逐次 boot (m11_boot_enter が InitUnits を回す) ではなく unit 隔離実行の測定。unit 間の状態は同一インスタンス内で引き継ぐ。
// trap した unit は影スタックを巻き戻して次へ進む (survey_trace.mjs と同じ)。abort した場合はそこで打ち切る。
import fs from 'fs';
import path from 'path';

const M11 = path.resolve(new URL('../', import.meta.url).pathname);
const args = process.argv.slice(2);
const cjs = path.resolve(args[0]);
const N = Number(args[1]);
const oi = args.indexOf('--out');
const outDir = oi >= 0 ? args[oi + 1] : null;
const TRACE = '/ftrace.jsonl';
const m2 = await import(cjs);
const image = fs.readFileSync(M11 + '/work/m11_image.bin');
const errs = [];
const mod = await (m2.default || m2)({ printErr: (s) => { errs.push(String(s)); if (errs.length > 400) errs.shift(); } });
mod.HEAPU8.set(image, 0);
mod._m11_set_survey(1);
const sp = mod._emscripten_stack_get_current();
try { mod._m11_boot_enter(0n, 1n); } catch (e) { if (!(e && e.m11_dllmain_done !== undefined)) throw e; mod.__emscripten_stack_restore(sp); }
mod.ccall('shimx_set_trace_file', 'number', ['string'], [TRACE]);
const nm = []; for (let k = 0; k < mod._sxt_n(); k++) nm.push(mod.UTF8ToString(mod._sxt_name(k)));
const FILEISH = /File|Find|Directory|Path/;
const sp0 = mod._emscripten_stack_get_current();
const perUnit = [];
let aborted = null;
for (let i = 0; i < N; i++) {
  const c0 = nm.map((_, k) => mod._sxt_count(k));
  let kind;
  try { const r = mod._m11_call_unit(i); kind = r === 1 ? 'ok' : r === 0 ? 'noproc' : r === 2 ? 'closure_outside' : 'range'; }
  catch (e) {
    if (e && e.m11_dllmain_done !== undefined) { kind = 'halt0'; try { mod.__emscripten_stack_restore(sp0); } catch (_) {} }
    else {
      const msg = ((e && e.message) || String(e)).split('\n')[0];
      kind = /Aborted|already aborted/.test(msg) ? 'abort' : /out of bounds/.test(msg) ? 'oob' : /unreachable/.test(msg) ? 'unreachable' : 'trap';
      if (kind === 'abort') { aborted = { unit: i + 1, msg }; break; }
      try { mod.__emscripten_stack_restore(sp0); } catch (_) {}
    }
  }
  const called = {}; nm.forEach((n, k) => { const d = mod._sxt_count(k) - c0[k]; if (d && FILEISH.test(n)) called[n] = d; });
  if (Object.keys(called).length) perUnit.push({ unit: i + 1, lva: '0x' + (mod._m11_unit_va(i) >>> 0).toString(16), kind, file_api_calls: called });
}
mod.ccall('shimx_set_trace_file', 'number', ['string'], [null]);
const text = Buffer.from(mod.FS.readFile(TRACE)).toString('utf8');
const lines = text.split('\n').filter(Boolean);
const byApi = {};
for (const l of lines) { try { const o = JSON.parse(l); byApi[o.api || '?'] = (byApi[o.api || '?'] || 0) + 1; } catch (_) { byApi['(parse error)'] = (byApi['(parse error)'] || 0) + 1; } }
if (outDir) { fs.mkdirSync(outDir, { recursive: true }); fs.writeFileSync(path.join(outDir, 'probe_t27.ftrace.jsonl'), text); }
console.log(JSON.stringify({ units_run_to: N, aborted, ftrace_lines: lines.length, by_api: byApi, units_with_file_api: perUnit, sample: lines.slice(0, 4) }, null, 1));
