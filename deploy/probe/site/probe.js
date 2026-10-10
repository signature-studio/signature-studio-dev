// 使い捨て probe ページ: 既定ホスト名 (workers.dev) + Static Assets + Access 配下で
//  isolation / SAB / Worker(COEP) / AudioWorklet / 分割 wasm の compileStreaming が成立することを 1 ページで検査する。結果は window.__probe
import { compileChunkedWasm, AccessExpiredError } from "./chunked.mjs";

const P = (window.__probe = { main: {}, worker: null, worklet: null, chunked: [], small: null, ce: null, errors: [] });
const guard = async (name, fn) => { try { return await fn(); } catch (e) { P.errors.push(`${name}: ${String(e?.stack ?? e).slice(0, 300)}`); return { error: String(e) }; } };

P.main.crossOriginIsolated = self.crossOriginIsolated;
P.main.sab = await guard("sab", async () => { new SharedArrayBuffer(8); return true; });
P.main.userAgent = navigator.userAgent;

P.worker = await guard("worker", () => new Promise((res, rej) => {
  const w = new Worker("./worker.js", { type: "module" });
  w.onmessage = (e) => { res(e.data); w.terminate(); };
  w.onerror = (e) => rej(new Error(`worker 起動失敗 ${e.message}`));
  setTimeout(() => rej(new Error("worker timeout")), 600000);
}));

P.worklet = await guard("worklet", async () => {
  const ctx = new OfflineAudioContext(1, 128, 44100);
  await ctx.audioWorklet.addModule("./worklet.js");
  const node = new AudioWorkletNode(ctx, "probe");
  const msg = new Promise((res) => (node.port.onmessage = (e) => res(e.data)));
  node.connect(ctx.destination);
  ctx.startRendering();
  return msg;
});

// 通常サイズ wasm (≤25MiB) は Static Assets の Content-Type: application/wasm で compileStreaming できる
P.small = await guard("small", async () => {
  const rel = await (await fetch("/release.json", { cache: "no-store" })).json();
  const key = Object.keys(rel.files).find((k) => k.startsWith("wasm/probe-small."));
  const t0 = performance.now();
  const resp = await fetch(`/${key}`);
  const ct = resp.headers.get("content-type");
  const m = await WebAssembly.compileStreaming(resp);
  return { key, ct, ms: Math.round(performance.now() - t0), exports: WebAssembly.Module.exports(m).length };
});

// 25MiB 超: part 連結 -> compileStreaming
const rel = await guard("release", async () => (await fetch("/release.json", { cache: "no-store" })).json());
for (const [key, c] of Object.entries(rel?.chunked ?? {})) {
  P.chunked.push(await guard(`chunked ${key}`, async () => {
    performance.clearResourceTimings();
    const t0 = performance.now();
    let last = null;
    const m = await compileChunkedWasm(`/${c.descriptor}`, { concurrency: 6, onProgress: (p) => (last = p) });
    const ms = Math.round(performance.now() - t0);
    const parts = performance.getEntriesByType("resource").filter((e) => e.name.endsWith(".part"));
    return {
      key, size: c.size, parts: c.parts, ms, MBps: +(c.size / 1e6 / (ms / 1000)).toFixed(1), exports: WebAssembly.Module.exports(m).length,
      partRequests: parts.length, partStatuses: [...new Set(parts.map((e) => e.responseStatus))], lastProgress: last,
    };
  }));
}

// _headers で Content-Encoding: br を付けた .br ファイルを fetch が復号するか (tools/assets の c/*.br 配置向けの事実確認)
P.ce = await guard("ce", async () => {
  const r = await fetch("/__probe__/ce/hello.br");
  return { status: r.status, contentEncoding: r.headers.get("content-encoding"), contentType: r.headers.get("content-type"), text: (await r.text()).slice(0, 40) };
});

document.title = "probe-done";
