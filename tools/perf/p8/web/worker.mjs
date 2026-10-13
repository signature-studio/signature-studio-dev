// Chrome Dedicated Worker 側: lib.mjs の one() を fetch ベースの env で実行する。
import { one } from '../lib.mjs';
let glue = null;
const env = {
  rd: async (f) => new Uint8Array(await (await fetch(`/w/${f}`)).arrayBuffer()),
  createMain: async () => {
    if (!glue) { glue = await (await fetch('/w/dyn_main.cjs')).text(); (0, eval)(glue); }
    const wasmBinary = new Uint8Array(await (await fetch('/w/dyn_main.wasm')).arrayBuffer());
    return globalThis.createMain({ instantiateWasm: (imports, cb) => { WebAssembly.instantiate(wasmBinary, imports).then((r) => cb(r.instance, r.module)); return {}; } });
  },
  rss: () => 0, hwm: () => 0, loadavg: () => [], info: {},
};
self.onmessage = async (ev) => {
  const m = ev.data;
  try { env.info = m.info; env.loadavg = () => m.loadavg; self.postMessage({ ok: true, r: await one(env, m.mode, m.cfg, m.N, m) }); }
  catch (e) { self.postMessage({ ok: false, error: String(e && e.stack || e) }); }
};
