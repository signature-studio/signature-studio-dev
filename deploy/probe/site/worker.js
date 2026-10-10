// 同一オリジン module Worker: COEP がスクリプト自体に付いていないと起動しない (tools/hosting 実測) ことの検査 + Worker 内での連結 wasm compile
import { compileChunkedWasm } from "./chunked.mjs";
const r = { crossOriginIsolated: self.crossOriginIsolated, sab: false };
try { new SharedArrayBuffer(8); r.sab = true; } catch (e) { r.sabError = String(e); }
try {
  const rel = await (await fetch("/release.json", { cache: "no-store" })).json();
  const key = Object.keys(rel.chunked ?? {})[0];
  if (key) {
    const t0 = performance.now();
    const m = await compileChunkedWasm(`/${rel.chunked[key].descriptor}`, { concurrency: 4 });
    r.chunkedCompile = { key, ms: Math.round(performance.now() - t0), exports: WebAssembly.Module.exports(m).length };
  }
} catch (e) { r.chunkedError = String(e?.stack ?? e).slice(0, 300); }
postMessage(r);
