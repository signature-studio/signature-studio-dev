const R = { env: {}, wasm: {}, js: {}, memory: {}, worker: {}, audio: {}, storage: {}, threads: {} };
window.__partial = R; window.__step = "start";
const t = async (sec, k, fn) => { window.__step = sec + "." + k; try { R[sec][k] = await Promise.race([fn(), new Promise((_, rej) => setTimeout(() => rej(new Error("step timeout 20s (hang)")), 20000))]); } catch (e) { R[sec][k] = "ERR: " + (e && e.message || e); } };
const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const feats = await (await fetch("./features.json")).json();

R.env = { ua: navigator.userAgent, hardwareConcurrency: navigator.hardwareConcurrency, deviceMemory: navigator.deviceMemory, crossOriginIsolated, isSecureContext };

for (const [k, v] of Object.entries(feats)) R.wasm[k] = v ? WebAssembly.validate(b64(v)) : null;

for (const [k, fn] of Object.entries({
  SharedArrayBuffer: () => typeof SharedArrayBuffer,
  Atomics_waitAsync: () => typeof Atomics.waitAsync,
  Atomics_wait_on_main: () => { try { Atomics.wait(new Int32Array(new SharedArrayBuffer(8)), 0, 0, 1); return "allowed"; } catch (e) { return "throws:" + e.name; } },
  JSPI_Suspending: () => typeof WebAssembly.Suspending,
  JSPI_promising: () => typeof WebAssembly.promising,
  compileStreaming: () => typeof WebAssembly.compileStreaming,
  Memory_address_i64_ctor: () => { try { new WebAssembly.Memory({ initial: 1n, address: "i64" }); return true; } catch (e) { return "ERR " + e.message; } },
  WebAssembly_Tag: () => typeof WebAssembly.Tag,
  WebAssembly_JSTag: () => typeof WebAssembly.JSTag,
  Memory_toResizableBuffer: () => typeof WebAssembly.Memory.prototype.toResizableBuffer,
  OffscreenCanvas: () => typeof OffscreenCanvas,
  transferControlToOffscreen: () => typeof HTMLCanvasElement.prototype.transferControlToOffscreen,
  AudioContext: () => typeof AudioContext,
  AudioWorklet: () => typeof AudioWorklet,
  WebGPU: () => typeof navigator.gpu,
  WebCodecs: () => typeof VideoDecoder,
  FileSystemAccess: () => typeof showOpenFilePicker,
  OPFS: () => typeof navigator.storage?.getDirectory,
  CacheStorage: () => typeof caches,
  IndexedDB: () => typeof indexedDB,
  WebMIDI: () => typeof navigator.requestMIDIAccess,
  WebHID: () => typeof navigator.hid,
  PointerLock: () => typeof document.body.requestPointerLock,
  Fullscreen: () => typeof document.body.requestFullscreen,
  structuredClone: () => typeof structuredClone,
})) await t("js", k, fn);

// --- memory limits (reservation only; ページ touch はしない) ---
const mem = async (k, fn) => { const t0 = performance.now(); await t("memory", k, async () => { const r = await fn(); return { ...r, ms: +(performance.now() - t0).toFixed(2) }; }); };
const GB = 16384; // pages per GB (64KiB)
await mem("wasm32_initial_4GB", () => { const m = new WebAssembly.Memory({ initial: 65536 }); return { ok: true, bytes: m.buffer.byteLength }; });
await mem("wasm32_initial_2GB_max_4GB", () => { const m = new WebAssembly.Memory({ initial: 2 * GB, maximum: 4 * GB }); return { ok: true, bytes: m.buffer.byteLength }; });
await mem("wasm32_grow_to_max", () => { const m = new WebAssembly.Memory({ initial: 256 }); let pages = 256, step = GB / 4; const t0 = performance.now(); while (pages < 4 * GB) { try { m.grow(Math.min(step, 4 * GB - pages)); pages = m.buffer.byteLength / 65536; } catch { break; } } return { reachedGB: pages / GB, growMs: +(performance.now() - t0).toFixed(1) }; });
await mem("shared32_initial_16_max_4GB", () => { const m = new WebAssembly.Memory({ initial: 16, maximum: 4 * GB, shared: true }); return { ok: true, bytes: m.buffer.byteLength, isSAB: m.buffer instanceof SharedArrayBuffer }; });
await mem("shared32_grow_to_4GB", () => { const m = new WebAssembly.Memory({ initial: 256, maximum: 4 * GB, shared: true }); let pages = 256; const t0 = performance.now(); while (pages < 4 * GB) { try { m.grow(GB / 4); pages = m.buffer.byteLength / 65536; } catch { break; } } return { reachedGB: pages / GB, growMs: +(performance.now() - t0).toFixed(1) }; });
await mem("shared32_initial_4GB", () => { const m = new WebAssembly.Memory({ initial: 4 * GB, maximum: 4 * GB, shared: true }); return { ok: true, bytes: m.buffer.byteLength }; });
await mem("mem64_initial_1p_max_16GB", () => { const m = new WebAssembly.Memory({ address: "i64", initial: 1n, maximum: BigInt(16 * GB) }); return { ok: true, bytes: m.buffer.byteLength }; });
await mem("mem64_grow_to_8GB", () => { const m = new WebAssembly.Memory({ address: "i64", initial: 256n }); let pages = 256; const t0 = performance.now(); while (pages < 8 * GB) { try { m.grow(BigInt(GB / 4)); pages = m.buffer.byteLength / 65536; } catch { break; } } return { reachedGB: pages / GB, growMs: +(performance.now() - t0).toFixed(1) }; });
await mem("mem64_shared_max_16GB", () => { const m = new WebAssembly.Memory({ address: "i64", initial: 16n, maximum: BigInt(16 * GB), shared: true }); return { ok: true, bytes: m.buffer.byteLength, isSAB: m.buffer instanceof SharedArrayBuffer }; });
await mem("mem64_shared_grow_to_8GB", () => { const m = new WebAssembly.Memory({ address: "i64", initial: 256n, maximum: BigInt(16 * GB), shared: true }); let pages = 256; const t0 = performance.now(); while (pages < 8 * GB) { try { m.grow(BigInt(GB / 4)); pages = m.buffer.byteLength / 65536; } catch { break; } } return { reachedGB: pages / GB, growMs: +(performance.now() - t0).toFixed(1) }; });
// JS ArrayBuffer 上限 (HEAPU8 view の制約)
await t("memory", "ArrayBuffer_8GB", () => { try { const b = new ArrayBuffer(8 * 2 ** 30); return { ok: true, len: b.byteLength }; } catch (e) { return "ERR " + e.message; } });
await t("memory", "wasm_memory_buffer_view_bigger_than_4GB_u8", () => { const m = new WebAssembly.Memory({ address: "i64", initial: BigInt(5 * GB) }); const u = new Uint8Array(m.buffer); return { ok: true, len: u.length }; });

// --- Worker 側 ---
const f_ret1 = b64((await (await fetch("./ret1.wasm.b64")).text()).trim());
const mod = new WebAssembly.Module(f_ret1);
await t("worker", "probe", () => new Promise((res, rej) => {
  const w = new Worker("./features.worker.js");
  w.onmessage = (e) => res(e.data); w.onerror = (e) => rej(new Error(e.message));
  w.postMessage({ mod });
  setTimeout(() => rej(new Error("worker probe timeout")), 20000);
}));

// --- 実スレッド: 共有 wasm memory + 4 worker で atomic add、memory.atomic.wait/notify ---
await t("threads", "wasm_atomic_add_4workers", async () => {
  const wasm = b64((await (await fetch("./thr.wasm.b64")).text()).trim());
  const memory = new WebAssembly.Memory({ initial: 1, maximum: 1, shared: true });
  const code = `onmessage=async e=>{const {wasm,memory,n}=e.data;const i=await WebAssembly.instantiate(wasm,{env:{memory}});i.instance.exports.inc(n);postMessage('done')}`;
  const url = URL.createObjectURL(new Blob([code], { type: "text/javascript" }));
  const N = 4, per = 1_000_000;
  const t0 = performance.now();
  await Promise.all(Array.from({ length: N }, () => new Promise((res) => { const w = new Worker(url); w.onmessage = () => { w.terminate(); res(); }; w.postMessage({ wasm, memory, n: per }); })));
  const v = new Int32Array(memory.buffer)[0];
  return { expected: N * per, got: v, ms: +(performance.now() - t0).toFixed(1) };
});
await t("threads", "wasm_atomic_wait_notify_cross_worker", async () => {
  const wasm = b64((await (await fetch("./thr.wasm.b64")).text()).trim());
  const memory = new WebAssembly.Memory({ initial: 1, maximum: 1, shared: true });
  const code = `onmessage=async e=>{const {wasm,memory}=e.data;const i=await WebAssembly.instantiate(wasm,{env:{memory}});postMessage('start');const r=i.instance.exports.waitflag();postMessage('woken:'+r)}`;
  const w = new Worker(URL.createObjectURL(new Blob([code], { type: "text/javascript" })));
  const log = [];
  await new Promise((res) => { w.onmessage = (e) => { log.push(e.data); if (e.data === "start") { const a = new Int32Array(memory.buffer); const t0 = performance.now(); (function poll() { Atomics.store(a, 1, 1); const n = Atomics.notify(a, 1, 1); if (n >= 1) res(); else setTimeout(poll, 5); })(); } if (String(e.data).startsWith("woken")) res(); }; w.postMessage({ wasm, memory }); });
  await new Promise((res) => { const f = () => (log.some((x) => String(x).startsWith("woken")) ? res() : setTimeout(f, 5)); f(); });
  w.terminate();
  return log;
});

// --- ストレージ ---
await t("storage", "estimate", async () => { const e = await navigator.storage.estimate(); return { quotaGB: +(e.quota / 2 ** 30).toFixed(1), usageMB: +(e.usage / 2 ** 20).toFixed(1) }; });
await t("storage", "idb_store_wasm_module", () => new Promise((res, rej) => {
  const rq = indexedDB.open("probe-mod", 1);
  rq.onupgradeneeded = () => rq.result.createObjectStore("m");
  rq.onerror = () => rej(new Error("idb open " + rq.error));
  rq.onsuccess = () => { try { const tx = rq.result.transaction("m", "readwrite"); tx.objectStore("m").put(mod, "k"); tx.oncomplete = () => res("stored"); tx.onerror = () => rej(new Error("tx " + tx.error?.name + ":" + tx.error?.message)); tx.onabort = () => rej(new Error("abort " + tx.error?.name)); } catch (e) { rej(new Error(e.name + ": " + e.message)); } };
}));
await t("storage", "cache_api_put_get", async () => { const c = await caches.open("probe"); await c.put("/x", new Response(new Uint8Array(1000))); const r = await c.match("/x"); await caches.delete("probe"); return (await r.arrayBuffer()).byteLength; });
await t("storage", "postMessage_module_structuredClone", () => { const m2 = structuredClone(mod); return m2 instanceof WebAssembly.Module; });

// --- Audio ---
await t("audio", "context", async () => {
  const ctx = new AudioContext({ latencyHint: "interactive" });
  await ctx.resume();
  const out = { state: ctx.state, sampleRate: ctx.sampleRate, baseLatency: ctx.baseLatency, outputLatency: ctx.outputLatency };
  const code = `class P extends AudioWorkletProcessor{constructor(o){super();this.sab=o.processorOptions.sab;this.a=new Int32Array(this.sab);this.n=0;
    try{Atomics.wait(this.a,2,0,0);this.waitOk='allowed'}catch(e){this.waitOk='throws:'+e.name}
    this.port.postMessage({hello:true,crossOriginIsolated:globalThis.crossOriginIsolated,sab:typeof SharedArrayBuffer,wasm:typeof WebAssembly,waitOk:this.waitOk,sampleRate:sampleRate})}
    process(i,o){this.n++;Atomics.store(this.a,0,this.n);return true}}
    registerProcessor('p',P)`;
  const url = URL.createObjectURL(new Blob([code], { type: "text/javascript" }));
  await ctx.audioWorklet.addModule(url);
  const sab = new SharedArrayBuffer(16);
  const node = new AudioWorkletNode(ctx, "p", { numberOfInputs: 0, outputChannelCount: [2], processorOptions: { sab } });
  const hello = new Promise((r) => (node.port.onmessage = (e) => r(e.data)));
  node.connect(ctx.destination);
  const a = new Int32Array(sab);
  const t0 = performance.now();
  while (Atomics.load(a, 0) < 200 && performance.now() - t0 < 10000) await new Promise((r) => setTimeout(r, 20));
  out.worklet = await Promise.race([hello, new Promise((r) => setTimeout(() => r("no hello"), 1000))]);
  out.processCalls = Atomics.load(a, 0);
  out.msFor200Blocks = +(performance.now() - t0).toFixed(0);
  await ctx.close();
  return out;
});
await t("audio", "canvas_main_transfer", async () => {
  const c = document.createElement("canvas"); c.width = 16; c.height = 16;
  const off = c.transferControlToOffscreen();
  const code = `onmessage=e=>{const g=e.data.c.getContext('webgl2');postMessage(g?g.getParameter(g.VERSION):null)}`;
  const w = new Worker(URL.createObjectURL(new Blob([code], { type: "text/javascript" })));
  const r = await new Promise((res) => { w.onmessage = (e) => res(e.data); w.postMessage({ c: off }, [off]); });
  w.terminate(); return r;
});

window.__result = R;
document.getElementById("o").textContent = JSON.stringify(R, null, 1);
