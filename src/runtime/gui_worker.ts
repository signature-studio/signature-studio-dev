/**
 * gui_worker.ts — 専用描画ワーカ。描画ロジックは gui_renderer.ts (fl-runtime Worker と共有)。
 *
 * 親 (main thread) への通知: log / frame (FRAME_END ack) / title / cursor / exit / readback 応答。
 */
import { GuiRenderer } from "./gui_renderer.js";

type InitMsg = { type: "init"; canvas: OffscreenCanvas; memory: WebAssembly.Memory; base: number; width: number; height: number };
type ReadbackMsg = { type: "readback"; id: number };
type BenchMsg = { type: "bench"; id: number; width: number; height: number; iters: number };

const ctx = self as unknown as DedicatedWorkerGlobalScope;
let renderer: GuiRenderer;

ctx.onmessage = (ev: MessageEvent<InitMsg | ReadbackMsg | BenchMsg>) => {
  const m = ev.data;
  if (m.type === "init") {
    renderer = new GuiRenderer({ canvas: m.canvas, memory: m.memory, base: m.base, width: m.width, height: m.height, post: (r) => ctx.postMessage(r) });
    ctx.postMessage({ type: "ready" });
    renderer.start();
  } else if (m.type === "bench") {
    const r = renderer.bench(m.width, m.height, m.iters);
    ctx.postMessage({ type: "bench", id: m.id, width: m.width, height: m.height, iters: m.iters, convertMs: r.convertMs, convertPutMs: r.convertPutMs });
  } else if (m.type === "readback") {
    const r = renderer.readback();
    ctx.postMessage({ type: "readback", id: m.id, width: r.width, height: r.height, data: r.data }, [r.data]);
  }
};
