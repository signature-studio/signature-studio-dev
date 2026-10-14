// PY-2 (#83): CPython + flapi provider を 1 つの wasm (flpy_static) にリンクした版の検証。
//   Worker / SAB / JS import / JSON 往復なし: node のメインスレッドで wasm を直接動かし、48 tool を実行して
//   (a) tool 別の status / result / api_calls / host_calls を SAB+provider 版 (tool_coverage.wasm.json) と
//   (b) 追跡中のモック版 (analysis/mcp/tool_coverage.json) の双方と突き合わせる。1 件でも差があれば exit 1。
//   node tests/static_check.mjs                       前提: build_flpy_static.sh と `FL_ENGINE=wasm node tests/all_tools.mjs` 済み
//   STATIC_WASM=flpy_static_neg  別ビルド (ネガコン) を使う。
//   比較ゲートは result の先頭 160 字だけを見る。全文の 3 経路比較は tests/fulltext_parity.mjs (FULLTEXT_OUT=<path> で全文を書く)。
import fs from "node:fs";
import assert from "node:assert/strict";
import { A } from "./tool_args.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const name = process.env.STATIC_WASM || "flpy_static";
const J = JSON.stringify;
let fails = 0;
const fail = (m) => { fails++; console.log("FAIL", m); };

const create = (await import(new URL(`dist/${name}.js`, root))).default;
const M = await create({ locateFile: (p) => new URL(`dist/${p}`, root).pathname, print() {}, printErr() {} });
for (const [path, file] of [["/fl/Lib/midi.py", "work/midi.py"], ["/fl/Lib/utils.py", "work/utils.py"], ["/fl/Tools/MCPTools.pyc", "work/MCPTools.pyc"]]) {
  M.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
  M.FS.writeFile(path, fs.readFileSync(new URL(file, root)));
}
const withStr = (s, f) => { const n = M.lengthBytesUTF8(s) + 1, p = M._malloc(n); M.stringToUTF8(s, p, n); try { return f(p); } finally { M._free(p); } };
const initRc = withStr("", (p) => M._flpy_init(p));
if (initRc !== 0) { console.log("flpy_init failed:", M.UTF8ToString(M._flpy_last_error())); process.exit(1); }
M._fl_engine_reset();
const run = (code) => { const rc = withStr(code, (c) => withStr("<static>", (f) => M._flpy_run(c, f))); if (rc !== 0) throw new Error(M.UTF8ToString(M._flpy_last_error())); };
const call = (target, args) => withStr(target, (t) => withStr(args == null ? "" : J(args), (a) => { const p = M._flpy_call_json(t, a); const s = M.UTF8ToString(p); M._flpy_free(p); return JSON.parse(s); }));

// 同一 wasm に provider が入っていて、JS 側 import `flhost_call` が無いこと (= JS 往復の排除) を wasm の import 表で確認する
const wasmBytes = fs.readFileSync(new URL(`dist/${name}.wasm`, root));
const mod = new WebAssembly.Module(wasmBytes);
const imports = WebAssembly.Module.imports(mod).map((i) => `${i.module}.${i.name}`);
const flImports = imports.filter((n) => /flhost|fl_api|flprov|flHostCall/i.test(n));
const exportsFl = WebAssembly.Module.exports(mod).map((e) => e.name).filter((n) => /fl_api_call|flpy_init/.test(n));
console.log(J({ wasm_bytes: wasmBytes.length, imports_total: imports.length, flhost_imports: flImports, exports: exportsFl }));
// ポジティブコントロール: JS 往復版 (flpy.wasm) は同じ正規表現に flhost_call import が掛かる = 検査が空振りしていない
const sabImports = WebAssembly.Module.imports(new WebAssembly.Module(fs.readFileSync(new URL("dist/flpy.wasm", root)))).map((i) => `${i.module}.${i.name}`).filter((n) => /flhost|fl_api|flprov|flHostCall/i.test(n));
if (!sabImports.some((n) => /flhost_call/.test(n))) fail("flpy.wasm (JS 往復版) に flhost_call import が見えない: import 検査が機能していない");
console.log(J({ sab_version_flhost_imports: sabImports }));
if (flImports.length) fail(`wasm が flhost 系の JS import を持つ: ${flImports}`);
if (!exportsFl.includes("fl_api_call")) fail("fl_api_call が wasm に存在しない");

run(`import fl_rt; fl_rt.install_flapi(); fl_rt.load_pyc("/fl/Tools/MCPTools.pyc", "__main__")`);
const tools = JSON.parse(call("__main__:get_mcp_tools_json", {}).ok);
const cov = [];
const full = [];
let total = 0;
M._flpy_trace_reset(1); // 以後の全呼出しを通し番号で記録 (tool 別は開始 index との差。tool 外の呼出し = callback 往復も総数に入る)
for (const t of tools) {
  const args = A[t.name];
  if (args === undefined) { cov.push({ name: t.name, status: "no-args-defined" }); continue; }
  const from = Number(M._flpy_host_calls());
  const r = call(`__main__:${t.name}`, args);
  const to = Number(M._flpy_host_calls());
  const n = to - from;
  assert.ok(to <= 65536, `trace overflow in ${t.name}`);
  const fnp = M._flpy_trace_fn(), ap = M._flpy_trace_argc();
  const calls = [];
  for (let i = from; i < to; i++) calls.push(`${ids[M.HEAPU8[fnp + 2 * i] | (M.HEAPU8[fnp + 2 * i + 1] << 8)]}/${M.HEAPU8[ap + i]}`);
  total += n;
  const text = r.err ? r.err : String(r.ok);
  full.push({ name: t.name, text });
  cov.push({
    name: t.name,
    status: r.err ? "raised" : /^(error|failed)/i.test(text) || /error/i.test(text.slice(0, 40)) ? "soft-error" : "ok",
    result: text.slice(0, 160),
    api_calls: [...new Set(calls)].sort(),
    host_calls: n,
  });
}
const hlId = Number(M._fl_engine_highlight_cb());
let cbOk = false;
if (hlId) { const r = call("fl_rt:invoke_cb", { id: hlId, args: [] }); cbOk = !r.err; }

const hostCallsAfterTools = Number(M._flpy_host_calls()); // 動的束縛の検証 (get_tempo 1 回) を数えない
// --- Py_* 動的束縛の対応表 (#83/#115): FL が LoadLibrary("Python312") 後に束縛する名前が、静的リンク版で全て解決できる ---
const map = JSON.parse(fs.readFileSync(new URL("analysis/pybind/pybind_map.json", root)));
const resolve = (n) => withStr(n, (p) => M._flpy_resolve(p));
const inLib = map.bindings.filter((b) => b.lib), absent = map.bindings.filter((b) => !b.lib);
let unresolved = inLib.filter((b) => resolve(b.name) === 0).map((b) => b.name);
if (unresolved.length) fail(`flpy_resolve が NULL: ${unresolved}`);
if (M._flpy_resolve_count() !== inLib.length) fail(`resolve 表 ${M._flpy_resolve_count()} != 対応表 ${inLib.length}`);
if (absent.some((b) => resolve(b.name) !== 0)) fail("lib に無い名前が解決された");
if (resolve("PyFoo_NoSuchApi") !== 0) fail("存在しない名前が解決された");
// 解決したアドレスを実際に呼ぶ (関数 = indirect function table index): Py_IsInitialized と、GIL 解放→再取得 (FL が UI/MIDI スレッドで使う SaveThread/RestoreThread)
const fnAt = (n) => M.wasmTable.get(resolve(n));
if (fnAt("Py_IsInitialized")() !== 1) fail("Py_IsInitialized != 1");
const ts = fnAt("PyEval_SaveThread")();
if (!ts) fail("PyEval_SaveThread が NULL");
fnAt("PyEval_RestoreThread")(ts);
if (fnAt("Py_IsInitialized")() !== 1) fail("RestoreThread 後に Py_IsInitialized != 1");
const afterGil = call("__main__:get_tempo", {});
if (afterGil.err || !/BPM/.test(String(afterGil.ok))) fail(`GIL 解放→再取得の後に tool が動かない: ${J(afterGil).slice(0, 120)}`);
console.log(J({ pybind_names: map.bindings.length, in_lib: inLib.length, resolved: inLib.length - unresolved.length, absent_documented: absent.map((b) => b.name) }));
const by = (s) => cov.filter((c) => c.status === s).length;
const summary = { total: cov.length, ok: by("ok"), soft_error: by("soft-error"), raised: by("raised"), no_args: by("no-args-defined"), host_calls: hostCallsAfterTools, host_calls_tools_sum: total, callback_roundtrip: cbOk };
console.log(J(summary));
fs.mkdirSync(new URL("work/", root), { recursive: true });
fs.writeFileSync(new URL(`work/tool_coverage.${name}.json`, root), J({ summary, tools: cov }, null, 1));
if (process.env.FULLTEXT_OUT) fs.writeFileSync(process.env.FULLTEXT_OUT, J({ engine: "static", tools: full }, null, 1));

// 比較: tool 別に完全一致 (差 0/48 を assert)。比較元が無い/短いこと自体を失敗にする
const refs = [
  ["SAB+provider (tool_coverage.wasm.json)", "analysis/mcp/tool_coverage.wasm.json"],
  ["mock (tool_coverage.json)", "analysis/mcp/tool_coverage.json"],
];
for (const [label, path] of refs) {
  if (!fs.existsSync(new URL(path, root))) { fail(`${label}: 比較元が無い (${path})`); continue; }
  const ref = JSON.parse(fs.readFileSync(new URL(path, root)));
  if (ref.tools.length !== cov.length) { fail(`${label}: tool 数 ${ref.tools.length} != ${cov.length}`); continue; }
  let diff = 0;
  for (const c of cov) {
    const o = ref.tools.find((x) => x.name === c.name);
    if (!o) { diff++; fail(`${label}: ${c.name} が比較元に無い`); continue; }
    for (const k of ["status", "result", "host_calls", "api_calls"]) {
      if (J(o[k]) !== J(c[k])) { diff++; fail(`${label}: ${c.name}.${k} 静的=${J(c[k]).slice(0, 100)} 比較元=${J(o[k]).slice(0, 100)}`); break; }
    }
  }
  console.log(`${label}: tool 別差 ${diff}/${cov.length}`);
  if (ref.summary.host_calls !== summary.host_calls || total !== ref.tools.reduce((a, x) => a + x.host_calls, 0)) fail(`${label}: host_calls 合計 ${summary.host_calls} != ${ref.summary.host_calls}`);
}
if (summary.ok !== 48 || summary.soft_error || summary.raised || summary.no_args || !cbOk) fail(`summary 不合格 ${J(summary)}`);
console.log(fails ? `STATIC CHECK FAIL (${fails})` : "STATIC CHECK OK");
process.exit(fails ? 1 : 0);
