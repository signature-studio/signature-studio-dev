// PY-2 (#83): 往復コスト (Python -> _flhost.call -> fl_api_call) を静的リンク版と Worker+SAB 版で同一プロセス・同一負荷下で計測する。
//   node tests/static_bench.mjs [trials=5]   出力: JSON (µs/呼出し。各 trial は 20,000 回、空ループ分を引いた値と引かない値)
import fs from "node:fs";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";

const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const trials = Number(process.argv[2] || 5), N = 20000;
const J = JSON.stringify;
const stats = (a) => ({ min: Math.min(...a), max: Math.max(...a), median: [...a].sort((x, y) => x - y)[a.length >> 1] });
const r3 = (x) => +x.toFixed(3);

// --- 静的リンク版 (同一 wasm 内。計時は Python の time.perf_counter で wasm 内側から) ---
const M = await (await import(new URL("dist/flpy_static.js", root))).default({ locateFile: (p) => new URL(`dist/${p}`, root).pathname, print() {}, printErr() {} });
const withStr = (s, f) => { const n = M.lengthBytesUTF8(s) + 1, p = M._malloc(n); M.stringToUTF8(s, p, n); try { return f(p); } finally { M._free(p); } };
withStr("", (p) => M._flpy_init(p)); M._fl_engine_reset();
const run = (c) => { if (withStr(c, (s) => withStr("<b>", (f) => M._flpy_run(s, f))) !== 0) throw new Error(M.UTF8ToString(M._flpy_last_error())); };
run(`import fl_rt, time; fl_rt.install_flapi(); import channels, mixer, _flhost
def bench(fn, n):
    t=time.perf_counter()
    for _ in range(n): fn()
    return (time.perf_counter()-t)*1e6/n
def empty(): pass
def run_bench(n):
    cid=${ids.indexOf("channels.channelCount")}; tid=${ids.indexOf("mixer.getTrackName")}
    f_raw=_flhost.call
    r={}
    r["empty_call_us"]=bench(empty,n)
    r["call_raw_us"]=bench(lambda: f_raw(cid, ()), n)          # _flhost.call 直 (戻り int)
    r["call_wrapped_us"]=bench(channels.channelCount, n)        # fl_api の薄ラッパ経由 (MCPTools が実際に通る経路)
    r["call_str_us"]=bench(lambda: f_raw(tid, (1,)), n)          # 戻り str (malloc/free + decode)
    return r
`);
const cBench = (fn, n) => Number(M._flpy_bench_c(ids.indexOf(fn), n)) / n / 1000; // µs
const staticRes = [];
for (let t = 0; t < trials; t++) {
  const out = withStr("__main__:run_bench", (tg) => withStr(J([N]), (a) => { const q = M._flpy_call_json(tg, a); const s = M.UTF8ToString(q); M._flpy_free(q); return JSON.parse(s); }));
  staticRes.push({ ...out.ok, c_only_us: cBench("channels.channelCount", N) /* Python 無し: C から fl_api_call のみ */ });
}
const keys = Object.keys(staticRes[0]);
const staticSummary = Object.fromEntries(keys.map((k) => [k, Object.fromEntries(Object.entries(stats(staticRes.map((r) => r[k]))).map(([a, b]) => [a, r3(b)]))]));

// --- Worker + SAB RPC 版 (PY-1 provider = C fl_api_call を JS 経由) ---
const engine = await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids });
const py = await FlPython.create({ flpyUrl: new URL("dist/flpy.js", root), engine, ids, files: {}, onStdout() {}, onStderr() {} });
await py.run("import fl_rt, time\nfl_rt.install_flapi()\nimport channels\ndef bench(n):\n    t=time.perf_counter()\n    for _ in range(n): channels.channelCount()\n    return (time.perf_counter()-t)*1e6/n\n");
const sab = [];
for (let t = 0; t < trials; t++) { const r = await py.call("__main__:bench", [N]); sab.push(r.ok); }
await py.terminate();
console.log(J({ n_per_trial: N, trials, load: fs.readFileSync("/proc/loadavg", "utf8").trim(), static: staticSummary, sab_worker: { call_wrapped_us: Object.fromEntries(Object.entries(stats(sab)).map(([a, b]) => [a, r3(b)])) }, raw_static: staticRes, raw_sab: sab }));
