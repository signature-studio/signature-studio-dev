// e2e ページ側: wasm (lifted app + shim) を起動して GuiHost を接続する。ドライバ (e2e.mjs) は window.__e2e を操作する。
import { GuiHost } from "/js/gui.js";

const W = 320, H = 200;
window.__e2e = { errors: [] };
window.addEventListener("error", (e) => window.__e2e.errors.push(String(e.message)));
window.__ready = (async () => {
  const mod = await createGuiApp({
    print: (s) => console.log("[wasm]", s),
    printErr: (s) => console.log("[wasm:err]", s),
  });
  const base = mod._gui_shared_ptr();
  const size = mod._gui_shared_size();
  const memory = mod.wasmMemory;
  const host = await GuiHost.attach({
    canvas: document.getElementById("screen"), memory, base, width: W, height: H,
    workerUrl: new URL("/js/gui_worker.js", location.href),
  });
  window.__e2e.host = host; window.__e2e.mod = mod; window.__e2e.memory = memory;
  return { base, size, crossOriginIsolated, sab: memory.buffer instanceof SharedArrayBuffer };
})();
