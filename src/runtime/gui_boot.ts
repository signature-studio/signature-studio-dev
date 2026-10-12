/**
 * gui_boot.ts — main thread 側の GUI 結線 (RT-3)。
 *   canvas.transferControlToOffscreen() → fl-runtime Worker (描画) / DOM 入力 → PumpRing.push (gui_input.ts)
 *
 * /?gui=selftest[&present=yield|blocking] で起動し、window.__gui に操作口を公開する (headless Chrome e2e が使う)。
 * ※ index.html の #screen は setupCanvas が 2d context を取得済みで transferControlToOffscreen できないため、
 *   GUI 結線用の canvas は別に生成する (FL 本体結合時は #screen の setupCanvas を外してこちらへ寄せる: 未解決参照)。
 */
import { PumpInput, type PumpInputStats } from "./gui_input";
import { spawnRuntimeWorker } from "./boot";
import type { FromWorker, GuiPresentMode, GuiSelfTestResult, ToWorker } from "./worker_protocol";
import { PumpRing, WM } from "./worker_pump";

export type GuiHandle = {
  state: "booting" | "ready" | "done" | "error";
  mode: GuiPresentMode;
  width: number;
  height: number;
  crossOriginIsolated: boolean;
  input?: PumpInputStats;
  result?: GuiSelfTestResult;
  error?: string;
  /** APP_RUNTIME_STOP を ring へ push して Worker の結果を待つ */
  finish: () => Promise<GuiSelfTestResult>;
  /** Worker を終了 (finish 後の画面確認を終えてから呼ぶ。terminate すると最終 commit 前に落ちる可能性がある) */
  terminate: () => void;
};

declare global {
  interface Window {
    __gui?: GuiHandle;
  }
}

export async function mountGuiSelfTest(params: URLSearchParams): Promise<void> {
  const mode: GuiPresentMode = params.get("present") === "blocking" ? "blocking" : "yield";
  const width = Number(params.get("w") ?? 320);
  const height = Number(params.get("h") ?? 200);
  const handle: GuiHandle = { state: "booting", mode, width, height, crossOriginIsolated, finish: () => Promise.reject(new Error("not ready")), terminate: () => {} };
  window.__gui = handle;
  try {
    if (!crossOriginIsolated) throw new Error("GUI 結線には crossOriginIsolated が必要");
    const canvas = document.createElement("canvas");
    canvas.id = "gui-canvas";
    canvas.width = width;
    canvas.height = height;
    canvas.style.cssText = `position:fixed;left:0;top:0;width:${width}px;height:${height}px;z-index:30;background:#000;outline:none`;
    document.body.appendChild(canvas);
    const offscreen = canvas.transferControlToOffscreen();
    const ring = PumpRing.create(1024);
    const worker = spawnRuntimeWorker();
    let resolveResult!: (r: GuiSelfTestResult) => void;
    let rejectResult!: (e: Error) => void;
    const resultP = new Promise<GuiSelfTestResult>((res, rej) => { resolveResult = res; rejectResult = rej; });
    const readyP = new Promise<void>((res) => {
      worker.onmessage = (ev: MessageEvent<FromWorker>) => {
        const m = ev.data;
        if (m.t === "gui-ready") res();
        else if (m.t === "gui-result") { handle.result = m.result; handle.state = "done"; resolveResult(m.result); }
        else if (m.t === "error") { handle.state = "error"; handle.error = m.message; rejectResult(new Error(m.message)); res(); }
      };
    });
    worker.onerror = (e) => { handle.state = "error"; handle.error = e.message; rejectResult(new Error(e.message)); };
    const msg: ToWorker = { t: "gui-selftest", ring: ring.sab, canvas: offscreen, width, height, present: mode };
    worker.postMessage(msg, [offscreen]);
    await readyP;
    if (handle.state === "error") return;
    // neg=1: 入力リスナーを付けない (e2e のネガティブコントロール: 入力系チェックが FAIL すべき)
    const input = new PumpInput({ canvas, ring });
    if (params.get("neg") === "1") input.dispose();
    handle.input = input.stats;
    handle.finish = async () => {
      input.flush();
      input.dispose();
      ring.push({ message: WM.APP_RUNTIME_STOP });
      return await resultP;
    };
    handle.terminate = () => worker.terminate();
    handle.state = "ready";
  } catch (e) {
    handle.state = "error";
    handle.error = String((e as Error)?.message ?? e);
  }
}

/**
 * /?gui=render-selftest — 合成 GuiShared (wasm 無し) で GuiHost → gui_worker (GuiRenderer) → OffscreenCanvas を検証する。
 * gui_worker.ts を gui_renderer.ts へ切り出した回帰確認 (実 shim 経由の tools/gui/e2e.sh は emsdk 必須)。
 * surface 0 = (10,10) 32x32 BGRA(0x10,0x80,0xf0) → 画面上は RGB(240,128,16)。
 */
export async function mountGuiRenderSelfTest(): Promise<void> {
  const { GuiHost } = await import("./gui");
  const { CMD, GUI_MAGIC, OFF, S, SURF_WORDS, W } = await import("./gui_proto");
  const out: { state: string; error?: string; frames?: number; readbackPixel?: number[]; logs?: string[] } = { state: "running" };
  (window as unknown as { __guiRender: typeof out }).__guiRender = out;
  try {
    const memory = new WebAssembly.Memory({ initial: 4, maximum: 4, shared: true });
    const base = 0;
    const i32 = new Int32Array(memory.buffer);
    const u32 = new Uint32Array(memory.buffer);
    const px = 0x20000;
    for (let i = 0; i < 32 * 32; i++) u32[(px >> 2) + i] = 0xff000000 | (0xf0 << 16) | (0x80 << 8) | 0x10; // BGRA(LE u32 = 0xAARRGGBB): R=0xf0 G=0x80 B=0x10
    Atomics.store(i32, W.magic, GUI_MAGIC);
    Atomics.store(i32, W.totalSize, OFF.total);
    const s = (OFF.surf >> 2) + 0 * SURF_WORDS;
    const set = (k: number, v: number) => { i32[s + k] = v; };
    set(S.visible, 1); set(S.x, 10); set(S.y, 10); set(S.w, 32); set(S.h, 32); set(S.stride, 128); set(S.pixels, px); set(S.z, 0);
    Atomics.store(i32, s + S.state, 1);
    const canvas = document.createElement("canvas");
    canvas.id = "gui-render-canvas";
    canvas.style.cssText = "position:fixed;left:0;top:0;width:320px;height:200px;z-index:30";
    document.body.appendChild(canvas);
    const host = await GuiHost.attach({ canvas, memory, base, width: 320, height: 200, worker: new Worker(new URL("./gui_worker.ts", import.meta.url), { type: "module", name: "gui-render" }) });
    const push = (w: number[]) => {
      const tail = Atomics.load(i32, W.outTail) >>> 0;
      const o = (OFF.outRecs >> 2) + (tail & 2047) * 8;
      for (let k = 0; k < 8; k++) u32[o + k] = w[k] ?? 0;
      Atomics.store(i32, W.outTail, (tail + 1) | 0);
      Atomics.notify(i32, W.outTail);
    };
    push([CMD.SURF_CREATE, 0]);
    push([CMD.PRESENT, 0, 0, 0, 32, 32, 1]);
    push([CMD.FRAME_END, 1]);
    await host.waitFrameAfter(0);
    const rb = await host.readback();
    const at = (x: number, y: number) => Array.from(rb.data.slice((y * rb.width + x) * 4, (y * rb.width + x) * 4 + 3));
    out.readbackPixel = at(20, 20);
    out.frames = host.frames;
    out.logs = host.logs;
    out.state = "done";
  } catch (e) {
    out.state = "error";
    out.error = String((e as Error)?.stack ?? e);
  }
}
