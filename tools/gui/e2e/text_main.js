// text_main.js — GUI-13 (#615) ブラウザ側: text_wasm_app (wasm) を起動し、face を遅延登録 (host call でフォント取得 + sha256 検証) して描画させる。
//   ?mode=normal  : face 登録あり (フォントは /fonts.json の url から取得し sha256 検証)
//   ?mode=nofont  : face 登録なし = shim は内蔵 8x8 フォント (ネガティブコントロール)
// ドライバ (text_e2e.mjs) は window.__ready / window.__run() を操作する。
import { GuiHost } from "/js/gui.js";
import { HostCallBridge, browserEnv } from "/js/gui_hostcall.js";
import { createFontLoader, registerFonts } from "/js/gui_fonts.js";

const W = 320, H = 120;
const mode = new URLSearchParams(location.search).get("mode") || "normal";
const T = (window.__t = { mode, events: [], host: null, bridge: null });
window.addEventListener("error", (e) => T.events.push("page error: " + e.message));

window.__ready = (async () => {
  const mod = await createGuiApp({ print: (s) => console.log("[wasm]", s), printErr: (s) => console.log("[wasm:err]", s) });
  const memory = mod.wasmMemory;
  const manifest = await (await fetch("/fonts.json")).json();   // [{name, url, sha256, file}]
  if (mode !== "nofont") {
    registerFonts(mod, manifest.map((m) => m.name), [["Segoe UI", "Open Sans"], ["Tahoma", "Open Sans"]]);
    const loadFont = createFontLoader(mod, manifest, { onEvent: (m) => T.events.push(m) });
    const noFs = { mkdirp() { throw new Error("no fs"); }, writeFile() { throw new Error("no fs"); }, readFile() { return null; } };
    T.bridge = new HostCallBridge(memory, mod._gui_hostcall_ptr(), { ...browserEnv(window, noFs), loadFont });
    T.bridge.start();
  }
  T.host = await GuiHost.attach({ canvas: document.getElementById("screen"), memory, base: mod._gui_shared_ptr(), width: W, height: H, workerUrl: new URL("/js/gui_worker.js", location.href) });
  return { crossOriginIsolated, sab: memory.buffer instanceof SharedArrayBuffer, mode };
})();

// 描画完了 ("text: done" = 最初の WM_PAINT 後) → present が追いつくまで待つ → desktop を worker から読み戻す
window.__run = async () => {
  const host = T.host;
  await host.waitLog("text: created");
  await host.waitLog("text: done");
  const v = host.view; const g = (i) => Atomics.load(v.i32, i) >>> 0;
  for (let i = 0; i < 500 && (g(37) !== g(38) || g(37) === 0); i++) await new Promise((r) => setTimeout(r, 20));
  const presentSeq = g(37), presentDone = g(38);
  const r = await host.readback(); let s = ""; const d = r.data;
  for (let i = 0; i < d.length; i += 0x8000) s += String.fromCharCode.apply(null, d.subarray(i, i + 0x8000));
  return { w: r.width, h: r.height, b64: btoa(s), tm: host.logs.filter((l) => l.startsWith("TM\t")).map((l) => l.slice(3)), logs: host.logs.filter((l) => !l.startsWith("TM\t")), events: T.events, presentSeq, presentDone };
};
