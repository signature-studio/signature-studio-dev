// P15 probe Worker: 実 OTT (ottl.wasm) を instance 化するだけ (駆動しない)。上限測定用。
const wasmP = fetch('/w/ottl.wasm').then((r) => r.arrayBuffer());
const imports = () => ({
  env: { _abort_js() { throw new Error('abort'); }, emscripten_resize_heap() { return 0; } },
  wasi_snapshot_preview1: { fd_close() { return 0; }, fd_write() { return 0; }, fd_seek() { return 0; } },
});
self.onmessage = async (ev) => {
  const { max } = ev.data;
  const bytes = await wasmP;
  const keep = []; let err = null;
  for (let i = 0; i < max; i++) {
    try { keep.push((await WebAssembly.instantiate(bytes, imports())).instance); } catch (e) { err = String(e && e.message || e).slice(0, 200); break; }
  }
  self.postMessage({ ok: keep.length, err });
};
