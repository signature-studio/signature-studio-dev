import { GuiHost } from "/js/gui.js";
window.__g6 = { errors: [] };
window.addEventListener("error", (e) => window.__g6.errors.push(String(e.message)));
window.__ready = (async () => {
  const mod = await createGuiApp({ print: () => {}, printErr: (s) => console.log("[wasm:err]", s) });
  const host = await GuiHost.attach({ canvas: document.getElementById("screen"), memory: mod.wasmMemory, base: mod._gui_shared_ptr(), width: 320, height: 200, workerUrl: new URL("/js/gui_worker.js", location.href) });
  // 要求された Pointer Lock をページ側で観測 (headless では requestPointerLock が即成立しない場合があるため呼出回数も数える)
  window.__g6.host = host; window.__g6.mod = mod;
  return { sab: mod.wasmMemory.buffer instanceof SharedArrayBuffer, crossOriginIsolated };
})();
