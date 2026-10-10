// Worker 側の機能検出。main から {features, cmd} を受け、結果を返す。
const R = {};
const t = async (k, fn) => { try { R[k] = await fn(); } catch (e) { R[k] = "ERR: " + (e && e.message || e); } };
self.onmessage = async (ev) => {
  const { sab, mod } = ev.data;
  R.crossOriginIsolated = self.crossOriginIsolated;
  await t("atomics_wait_in_worker", () => { const a = new Int32Array(new SharedArrayBuffer(16)); return Atomics.wait(a, 0, 0, 5); });
  await t("atomics_waitAsync", () => typeof Atomics.waitAsync);
  await t("nested_worker", () => new Promise((res, rej) => {
    const w = new Worker(URL.createObjectURL(new Blob(["postMessage('nested-ok')"], { type: "text/javascript" })));
    w.onmessage = (e) => res(e.data); w.onerror = (e) => rej(new Error(e.message || "nested worker error"));
    setTimeout(() => rej(new Error("timeout")), 5000);
  }));
  await t("offscreen_canvas_2d", () => { const c = new OffscreenCanvas(8, 8); const x = c.getContext("2d"); x.fillStyle = "#f00"; x.fillRect(0, 0, 8, 8); return x.getImageData(0, 0, 1, 1).data[0]; });
  await t("offscreen_canvas_webgl2", () => { const c = new OffscreenCanvas(8, 8); const g = c.getContext("webgl2"); return g ? g.getParameter(g.VERSION) : null; });
  await t("offscreen_canvas_webgl2_renderer", () => { const c = new OffscreenCanvas(8, 8); const g = c.getContext("webgl2"); const e = g && g.getExtension("WEBGL_debug_renderer_info"); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : null; });
  await t("worker_rAF", () => typeof self.requestAnimationFrame);
  await t("opfs_sync_access_handle", async () => {
    const root = await navigator.storage.getDirectory();
    const fh = await root.getFileHandle("probe.bin", { create: true });
    const h = await fh.createSyncAccessHandle();
    const w = h.write(new Uint8Array([1, 2, 3]), { at: 0 }); h.flush(); h.close();
    await root.removeEntry("probe.bin");
    return "write=" + w;
  });
  await t("idb_in_worker", () => typeof indexedDB);
  await t("module_from_main_instantiate", async () => {
    const inst = await WebAssembly.instantiate(mod);
    return inst.exports.f();
  });
  await t("shared_memory_wasm_threads", async () => {
    // main が渡した shared Memory に対し 4 worker で atomic add (別途 main 側で実施)
    return "see main";
  });
  await t("webgpu", () => typeof navigator.gpu);
  await t("hardwareConcurrency", () => navigator.hardwareConcurrency);
  postMessage(R);
};
