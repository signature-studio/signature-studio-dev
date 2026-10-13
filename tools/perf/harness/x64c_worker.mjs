// Chrome Dedicated Worker 内で bit-exact OTT (x64c wasm) を計測 (x64c_node.mjs と同一手順・同一 core)。
import { setupOtt, measure } from './x64c_core.mjs';
self.onmessage = async (e) => {
  try {
    const { variant, iters = 20000, head = 300, streaming = true } = e.data;
    const out = { env: 'chrome-worker', variant, crossOriginIsolated: self.crossOriginIsolated, ua: navigator.userAgent };
    const url = `/w/ott_x64c/${variant}.wasm`;
    const t0 = performance.now();
    const mod = streaming ? await WebAssembly.compileStreaming(fetch(url)) : await WebAssembly.compile(await (await fetch(url)).arrayBuffer());
    out.compileMs = performance.now() - t0;
    const t1 = performance.now();
    const names = await (await fetch(`/w/ott_x64c/${variant}.names.json`)).json();
    const o = await setupOtt(mod, names);
    out.setupMs = performance.now() - t1;
    out.memBytes = o.memBytes;
    out.signature = o.signature(); out.nonzeroOut = o.nonzero();
    const r = measure(o.call, () => performance.now(), { iters, head });
    out.head = r.head.map((x) => +x.toFixed(4)); out.steady = r.steady; out.batch64 = r.batch64;
    out.rtf44 = r.steady.p50 / (128 / 44.1); out.rtf44p99 = r.steady.p99 / (128 / 44.1);
    postMessage({ type: 'done', result: out });
  } catch (err) { postMessage({ type: 'err', msg: String(err && err.stack || err) }); }
};
