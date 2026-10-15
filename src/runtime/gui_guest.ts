/**
 * gui_guest.ts — /?gui=wasm&glue=<app.js URL>&app=<descriptor URL>[&w=&h=] で、ゲスト wasm を製品ページに載せる (WIN-24 #3461)。
 *   descriptor (<asset>.parts/index.json) → fetchCompile (chunked・sha256 検証) → glue の createGuiApp (instantiateWasm で注入)
 *   → GuiHost.attach (専用 canvas #gui-canvas) → onFrame → window.__webstudio.frames
 *
 * ゲストは FL ではない検証用の wasm (tools/gui/test/text_wasm_app.c)。契約の guest は "test" (fl-boot は PASS しない: D5)。
 * 入力経路 (PumpInput / GuiShared の入力リング) はまだ結線しない。#screen へは描かない。
 */
import { fetchCompile } from "./loader_boot";
import type { GuiHost } from "./gui";
import type { WebstudioController } from "./webstudio_state";

type GuiAppModule = { wasmMemory: WebAssembly.Memory; _gui_shared_ptr: () => number };
type GuiAppFactory = (m: Record<string, unknown>) => Promise<GuiAppModule>;

declare global {
  interface Window {
    /** 起動したゲストの GuiHost (e2e が readback で画素を読む) */
    __guiGuest?: GuiHost;
  }
}

function loadScript(src: string): Promise<void> {
  return new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = () => res();
    s.onerror = () => rej(new Error(`glue の読込に失敗: ${src}`));
    document.head.appendChild(s);
  });
}

export async function mountGuiGuest(params: URLSearchParams, ctl: WebstudioController): Promise<void> {
  const glueUrl = params.get("glue");
  const appUrl = params.get("app");
  const width = Number(params.get("w") ?? 320);
  const height = Number(params.get("h") ?? 120);
  ctl.setGuest("test");
  try {
    if (!crossOriginIsolated) throw new Error("GUI guest には crossOriginIsolated が必要");
    if (!glueUrl || !appUrl) throw new Error("glue と app (descriptor URL) の指定が必要");
    const { module } = await fetchCompile(appUrl, { cacheMode: "none", compile: "streaming" });
    await loadScript(glueUrl);
    const createGuiApp = (window as unknown as { createGuiApp?: GuiAppFactory }).createGuiApp;
    if (!createGuiApp) throw new Error(`glue ${glueUrl} が createGuiApp を定義しない`);
    const mod = await createGuiApp({
      instantiateWasm: (imports: WebAssembly.Imports, done: (i: WebAssembly.Instance, m: WebAssembly.Module) => void) => {
        WebAssembly.instantiate(module, imports).then((inst) => done(inst, module), (e) => ctl.fail(e));
        return {};
      },
      print: (s: string) => console.log("[guest]", s),
      printErr: (s: string) => console.log("[guest:err]", s),
    });
    const canvas = document.createElement("canvas");
    canvas.id = "gui-canvas";
    canvas.style.cssText = `position:fixed;left:0;top:0;width:${width}px;height:${height}px;z-index:30;outline:none`;
    document.body.appendChild(canvas);
    const { GuiHost } = await import("./gui");
    window.__guiGuest = await GuiHost.attach({
      canvas,
      memory: mod.wasmMemory,
      base: mod._gui_shared_ptr(),
      width,
      height,
      worker: new Worker(new URL("./gui_worker.ts", import.meta.url), { type: "module", name: "gui-guest" }),
      onFrame: (n) => ctl.setFrames(n),
    });
  } catch (e) {
    ctl.fail(e);
  }
}
