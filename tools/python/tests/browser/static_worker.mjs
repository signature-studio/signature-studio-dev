// PY-81 (#2634): 静的版 flpy_static (CPython + provider を 1 wasm にリンク) を module Worker 内で動かす。
//   JS import・SAB・JSON 往復の無い経路。48 tool を実行し、tool 別の status / result / api_calls / host_calls を返す。
//   集計の作り方は tests/static_check.mjs と同じ (trace 通し番号の差分で tool 別 host_calls を数える)。
import { A } from "/tests/tool_args.mjs";

const J = JSON.stringify;
const get = async (p) => new Uint8Array(await (await fetch(p)).arrayBuffer());

async function runStatic() {
  const t0 = performance.now();
  const ids = await (await fetch("/analysis/flapi/flapi_ids.json")).json();
  const create = (await import("/dist/flpy_static.js")).default;
  const M = await create({
    locateFile: (p) => new URL(`/dist/${p}`, self.location.href).href,
    print() {}, printErr() {},
  });
  for (const [path, file] of [["/fl/Lib/midi.py", "/work/midi.py"], ["/fl/Lib/utils.py", "/work/utils.py"], ["/fl/Tools/MCPTools.pyc", "/work/MCPTools.pyc"]]) {
    M.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
    M.FS.writeFile(path, await get(file));
  }
  const withStr = (s, f) => { const n = M.lengthBytesUTF8(s) + 1, p = M._malloc(n); M.stringToUTF8(s, p, n); try { return f(p); } finally { M._free(p); } };
  if (withStr("", (p) => M._flpy_init(p)) !== 0) throw new Error("flpy_init failed: " + M.UTF8ToString(M._flpy_last_error()));
  const initMs = Math.round(performance.now() - t0);
  M._fl_engine_reset();
  const run = (code) => { const rc = withStr(code, (c) => withStr("<static>", (f) => M._flpy_run(c, f))); if (rc !== 0) throw new Error(M.UTF8ToString(M._flpy_last_error())); };
  const call = (target, args) => withStr(target, (t) => withStr(args == null ? "" : J(args), (a) => { const p = M._flpy_call_json(t, a); const s = M.UTF8ToString(p); M._flpy_free(p); return JSON.parse(s); }));
  run(`import fl_rt; fl_rt.install_flapi(); fl_rt.load_pyc("/fl/Tools/MCPTools.pyc", "__main__")`);
  const tools = JSON.parse(call("__main__:get_mcp_tools_json", {}).ok);
  const cov = [];
  M._flpy_trace_reset(1);
  const t1 = performance.now();
  for (const t of tools) {
    const args = A[t.name];
    if (args === undefined) { cov.push({ name: t.name, status: "no-args-defined" }); continue; }
    const from = Number(M._flpy_host_calls());
    const r = call(`__main__:${t.name}`, args);
    const to = Number(M._flpy_host_calls());
    const fnp = M._flpy_trace_fn(), ap = M._flpy_trace_argc();
    const calls = [];
    for (let i = from; i < to; i++) calls.push(`${ids[M.HEAPU8[fnp + 2 * i] | (M.HEAPU8[fnp + 2 * i + 1] << 8)]}/${M.HEAPU8[ap + i]}`);
    const text = r.err ? r.err : String(r.ok);
    cov.push({
      name: t.name,
      status: r.err ? "raised" : /^(error|failed)/i.test(text) || /error/i.test(text.slice(0, 40)) ? "soft-error" : "ok",
      result: text.slice(0, 160),
      api_calls: [...new Set(calls)].sort(),
      host_calls: to - from,
    });
  }
  const toolsMs = Math.round(performance.now() - t1);
  const hlId = Number(M._fl_engine_highlight_cb());
  let cbOk = false;
  if (hlId) { const r = call("fl_rt:invoke_cb", { id: hlId, args: [] }); cbOk = !r.err; }
  const by = (s) => cov.filter((c) => c.status === s).length;
  const in_worker = typeof WorkerGlobalScope !== "undefined" && self instanceof WorkerGlobalScope;
  const summary = { total: cov.length, ok: by("ok"), soft_error: by("soft-error"), raised: by("raised"), no_args: by("no-args-defined"), host_calls: Number(M._flpy_host_calls()), callback_roundtrip: cbOk, init_ms: initMs, tools_ms: toolsMs, in_worker };
  return { summary, tools: cov };
}

self.onmessage = async (e) => {
  try {
    postMessage({ id: e.data.id, ok: await runStatic() });
  } catch (err) {
    postMessage({ id: e.data.id, err: String(err && err.stack || err) });
  }
};
