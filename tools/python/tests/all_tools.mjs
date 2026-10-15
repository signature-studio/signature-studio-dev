// 48 tools を wasm CPython(Worker)+モック上で全実行し、各 tool の成否と実際に呼ばれた flapi (引数個数付き) を記録する。
//   node tests/all_tools.mjs  ->  analysis/mcp/tool_coverage.json
import fs from "node:fs";
import { FlPython } from "../host/flpython.mjs";
import { createMockEngine } from "../host/fl_mock.mjs";
import { createWasmEngine } from "../host/fl_provider.mjs";
import { A } from "./tool_args.mjs";

// FL_ENGINE=wasm: provider/ の C 実装 (fl_api_call) を使う。既定は JS モック。
//   wasm のとき analysis/mcp/tool_coverage.json は更新せず tool_coverage.wasm.json に書く。
//   FULLTEXT_OUT=<path>: 全文 (切り詰めなし) を path に書き、analysis/ の json は更新しない (fulltext_parity.mjs 用)。
const root = new URL("../", import.meta.url);
const ids = JSON.parse(fs.readFileSync(new URL("analysis/flapi/flapi_ids.json", root)));
const useWasm = process.env.FL_ENGINE === "wasm";
const engine = useWasm ? await createWasmEngine({ flprovUrl: new URL("dist/flprov.js", root), ids }) : createMockEngine();
const py = await FlPython.create({
  flpyUrl: new URL("dist/flpy.js", root), engine, ids,
  files: {
    "/fl/Lib/midi.py": fs.readFileSync(new URL("work/midi.py", root)),
    "/fl/Lib/utils.py": fs.readFileSync(new URL("work/utils.py", root)),
    "/fl/Tools/MCPTools.pyc": fs.readFileSync(new URL("work/MCPTools.pyc", root)),
  },
  onStdout: () => {}, onStderr: () => {},
});
await py.run(`import fl_rt; fl_rt.install_flapi(); fl_rt.load_pyc("/fl/Tools/MCPTools.pyc", "__main__")`);

const J = JSON.stringify;
const tools = JSON.parse((await py.call("__main__:get_mcp_tools_json", {})).ok);
const cov = [];
const full = [];
for (const t of tools) {
  const args = A[t.name];
  if (args === undefined) { cov.push({ name: t.name, status: "no-args-defined" }); continue; }
  const before = engine.record.length;
  const r = await py.call(`__main__:${t.name}`, args);
  const calls = engine.record.slice(before).map(([n, a]) => `${n}/${a.length}`);
  const text = r.err ? r.err : String(r.ok);
  full.push({ name: t.name, text });
  cov.push({
    name: t.name,
    status: r.err ? "raised" : /^(error|failed)/i.test(text) || /error/i.test(text.slice(0, 40)) ? "soft-error" : "ok",
    result: text.slice(0, 160),
    api_calls: [...new Set(calls)].sort(),
    host_calls: calls.length,
  });
}
// ilmcp.showHighlight に渡された Python callable (whenDone) をホスト側から呼び戻す
const hlId = useWasm ? engine.highlightCb() : engine.state.highlight?.cb?.__cb;
let cbOk = false;
if (hlId) { const r = await py.call("fl_rt:invoke_cb", { id: hlId, args: [] }); cbOk = !r.err; }
await py.terminate();
const by = (s) => cov.filter((c) => c.status === s).length;
const summary = { total: cov.length, ok: by("ok"), soft_error: by("soft-error"), raised: by("raised"), no_args: by("no-args-defined"), host_calls: engine.record.length, callback_roundtrip: cbOk };
if (process.env.FULLTEXT_OUT) fs.writeFileSync(process.env.FULLTEXT_OUT, J({ engine: useWasm ? "wasm" : "mock", tools: full }, null, 1));
else fs.writeFileSync(new URL(useWasm ? "analysis/mcp/tool_coverage.wasm.json" : "analysis/mcp/tool_coverage.json", root), J({ summary, tools: cov }, null, 1));
console.log(J(summary));
for (const c of cov.filter((c) => c.status !== "ok")) console.log(c.status, c.name, (c.result || "").replace(/\n/g, " ").slice(0, 160));
