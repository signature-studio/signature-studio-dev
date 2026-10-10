// メインスレッド側 API: wasm Python Worker を起動し、FLEngine(engine) へ flapi 呼出しを橋渡しする。
//   const py = await FlPython.create({ flpyUrl, engine, files })
//   await py.run("print(1)")             // __main__ で実行
//   await py.call("MCPTools:play", {})   // "module:func" を JSON 引数で呼ぶ → {ok}|{err}
//   engine = { call(name:"mixer.getTrackName", args:any[]) -> any }  同期/非同期どちらも可
import { createRpcBuffer, RpcServer } from "./rpc.mjs";

export class FlPython {
  static async create({ flpyUrl, engine, ids, files = {}, syspath = "", workerUrl, onStdout, onStderr }) {
    const self = new FlPython();
    self.onStdout = onStdout || ((t) => console.log("[py]", t));
    self.onStderr = onStderr || ((t) => console.error("[py!]", t));
    self.sab = createRpcBuffer();
    self.ids = ids;
    self.calls = 0;
    self.server = new RpcServer(self.sab, async ({ fn, args }) => {
      self.calls++;
      return engine.call(ids[fn], args);
    });
    workerUrl = workerUrl || new URL("./py_worker.mjs", import.meta.url);
    if (typeof Worker !== "undefined") {
      self.w = new Worker(workerUrl, { type: "module" });
      self.w.onmessage = (e) => self.#onMsg(e.data);
    } else {
      const { Worker: NW } = await import("node:worker_threads");
      const { fileURLToPath } = await import("node:url");
      self.w = new NW(fileURLToPath(workerUrl));
      self.w.on("message", (m) => self.#onMsg(m));
      self.w.on("error", (e) => self.#fail(e));
    }
    self.pending = new Map();
    self.seq = 0;
    await self.#req({ type: "init", sab: self.sab, flpyUrl: String(flpyUrl), files, syspath });
    return self;
  }
  #onMsg(m) {
    if (m.type === "stdout") return this.onStdout(m.text);
    if (m.type === "stderr") return this.onStderr(m.text);
    const p = this.pending.get(m.id);
    if (!p) return;
    this.pending.delete(m.id);
    m.err !== undefined ? p.reject(new Error(m.err)) : p.resolve(m.ok);
  }
  #fail(e) { for (const p of this.pending.values()) p.reject(e); this.pending.clear(); }
  #req(msg) {
    return new Promise((resolve, reject) => {
      const id = ++this.seq;
      this.pending.set(id, { resolve, reject });
      this.w.postMessage({ ...msg, id });
    });
  }
  run(code, filename) { return this.#req({ type: "run", code, filename }); }
  call(target, args) { return this.#req({ type: "call", target, args }); }
  async terminate() { this.server.stop(); await this.w.terminate(); }
}
