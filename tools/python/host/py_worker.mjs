// Worker 側: wasm CPython を起動し、_flhost の境界を SAB 同期 RPC に接続する。
// ブラウザ (module Worker) / Node (worker_threads) 両対応。
import { RpcClient } from "./rpc.mjs";

const isBrowserWorker = typeof WorkerGlobalScope !== "undefined" && globalThis instanceof WorkerGlobalScope;
let port;
if (isBrowserWorker) {
  port = { on: (cb) => { globalThis.onmessage = (e) => cb(e.data); }, post: (m) => globalThis.postMessage(m) };
} else {
  const wt = await import("node:worker_threads");
  port = { on: (cb) => wt.parentPort.on("message", cb), post: (m) => wt.parentPort.postMessage(m) };
}

let M = null;       // Emscripten module
let client = null;  // RpcClient

function cstr(s) {
  const n = M.lengthBytesUTF8(s) + 1;
  const p = M._malloc(n);
  M.stringToUTF8(s, p, n);
  return p;
}
function withStrs(strs, fn) {
  const ps = strs.map((s) => (s == null ? 0 : cstr(s)));
  try { return fn(...ps); } finally { ps.forEach((p) => p && M._free(p)); }
}

async function init({ sab, flpyUrl, files = {}, syspath = "" }) {
  client = new RpcClient(sab);
  const create = (await import(flpyUrl)).default;
  const locateFile = isBrowserWorker
    ? (p) => new URL(p, flpyUrl).href
    : (p) => new URL(p, flpyUrl).pathname;
  M = await create({
    locateFile,
    print: (t) => port.post({ type: "stdout", text: t }),
    printErr: (t) => port.post({ type: "stderr", text: t }),
    flHostCall: (fnId, args) => {
      const r = client.call({ fn: fnId, args });
      if (r.err !== undefined) {
        const e = new Error(r.err);
        e.flCode = r.code;
        throw e;
      }
      return r.ok;
    },
  });
  for (const [path, content] of Object.entries(files)) {
    const dir = path.slice(0, path.lastIndexOf("/"));
    if (dir) M.FS.mkdirTree(dir);
    M.FS.writeFile(path, content);
  }
  const rc = withStrs([syspath], (p) => M._flpy_init(p));
  if (rc !== 0) throw new Error("flpy_init failed: " + M.UTF8ToString(M._flpy_last_error()));
  return rc;
}

const handlers = {
  async init(m) { await init(m); return { python: true }; },
  run({ code, filename }) {
    const rc = withStrs([code, filename || "<flpy>"], (c, f) => M._flpy_run(c, f));
    if (rc !== 0) throw new Error(M.UTF8ToString(M._flpy_last_error()));
    return rc;
  },
  call({ target, args }) {
    return withStrs([target, args == null ? "" : JSON.stringify(args)], (t, a) => {
      const p = M._flpy_call_json(t, a);
      const s = M.UTF8ToString(p);
      M._flpy_free(p);
      return JSON.parse(s);
    });
  },
};

port.on(async (m) => {
  try {
    const out = await handlers[m.type](m);
    port.post({ id: m.id, ok: out });
  } catch (e) {
    port.post({ id: m.id, err: String(e && e.stack || e) });
  }
});
