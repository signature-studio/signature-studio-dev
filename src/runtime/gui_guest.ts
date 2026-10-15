/**
 * gui_guest.ts — /?gui=wasm&glue=<app.js URL>&app=<descriptor URL>[&w=&h=] で、ゲスト wasm を製品ページに載せる (WIN-24 #3461)。
 *   descriptor (<asset>.parts/index.json) → fetchCompile (chunked・sha256 検証) → glue の createGuiApp (instantiateWasm で注入)
 *   → GuiHost.attach (専用 canvas #gui-canvas) → onFrame → window.__webstudio.frames
 *
 * ゲストは FL ではない検証用の wasm (tools/gui/test/text_wasm_app.c)。契約の guest は "test"。
 * glue と app は同一オリジンの URL だけ読む (src/runtime/same_origin.ts)。fl-boot は guest === "fl" を要求するので PASS しない。
 * 入力経路 (PumpInput / GuiShared の入力リング) はまだ結線しない。#screen へは描かない。
 */
import { fetchCompile } from "./loader_boot";
import { resolveSameOriginUrl } from "./same_origin";
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
  const glueParam = params.get("glue");
  const appParam = params.get("app");
  const width = Number(params.get("w") ?? 320);
  const height = Number(params.get("h") ?? 120);
  ctl.setGuest("test");
  try {
    if (!crossOriginIsolated) throw new Error("GUI guest には crossOriginIsolated が必要");
    if (!glueParam || !appParam) throw new Error("glue と app (descriptor URL) の指定が必要");
    const glueUrl = resolveSameOriginUrl(glueParam, location.href);
    const appUrl = resolveSameOriginUrl(appParam, location.href);
    const { module } = await fetchCompile(appUrl, { cacheMode: "none", compile: "streaming" });
    await loadScript(glueUrl);
    const createGuiApp = (window as unknown as { createGuiApp?: GuiAppFactory }).createGuiApp;
    if (!createGuiApp) throw new Error(`glue ${glueUrl} が createGuiApp を定義しない`);
    // instantiate の失敗は createGuiApp の失敗として返す (done が呼ばれず await が止まるのを防ぐ)
    const mod = await new Promise<GuiAppModule>((resolve, reject) => {
      createGuiApp({
        instantiateWasm: (imports: WebAssembly.Imports, done: (i: WebAssembly.Instance, m: WebAssembly.Module) => void) => {
          WebAssembly.instantiate(module, imports).then((inst) => done(inst, module), reject);
          return {};
        },
        print: (s: string) => console.log("[guest]", s),
        printErr: (s: string) => console.log("[guest:err]", s),
      }).then(resolve, reject);
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
