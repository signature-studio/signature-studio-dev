/**
 * gui_worker.ts — 描画ワーカ。out ring (shim -> host コマンド) を消費して OffscreenCanvas(2D) へ合成する。
 *
 * - 共有領域は wasm の WebAssembly.Memory 上 (SAB)。メモリ成長に追従するため呼出ごとに memory.buffer を取り直す。
 * - surface ピクセルは BGRA32 top-down。dirty 矩形のみ RGBA へ変換して putImageData (alpha は 255 に固定)。
 * - z-order: 描画した矩形に重なるより前面の surface を再描画して前後関係を保つ。
 * - 待機は Atomics.waitAsync(out_ring.tail) によるイベント駆動 (ポーリング/sleep 無し)。
 * - 親 (main thread) への通知: log / frame (FRAME_END ack) / title / cursor / exit / readback 応答。
 */
import { CMD, GUI_MAX_SURF, GUI_OUT_RECS, GuiView, OFF, S, SURF_WORDS, W } from "./gui_proto.js";

type InitMsg = { type: "init"; canvas: OffscreenCanvas; memory: WebAssembly.Memory; base: number; width: number; height: number };
type ReadbackMsg = { type: "readback"; id: number };
type BenchMsg = { type: "bench"; id: number; width: number; height: number; iters: number };

const ctx = self as unknown as DedicatedWorkerGlobalScope;
let view: GuiView;
let memory: WebAssembly.Memory;
let base = 0;
let g2d: OffscreenCanvasRenderingContext2D;
let canvasW = 0, canvasH = 0;
let logAcc = "";
let framesDone = 0;

function refresh(): GuiView {
  if (view.buffer !== memory.buffer) view = new GuiView(memory.buffer, base);
  return view;
}

type Surf = { id: number; state: number; visible: number; x: number; y: number; w: number; h: number; stride: number; pixels: number; z: number };
function surf(v: GuiView, id: number): Surf {
  const o = (OFF.surf >> 2) + id * SURF_WORDS;
  const u = v.u32, i = v.i32;
  return { id, state: Atomics.load(i, o + S.state), visible: u[o + S.visible], x: i[o + S.x], y: i[o + S.y], w: u[o + S.w], h: u[o + S.h],
           stride: u[o + S.stride], pixels: u[o + S.pixels], z: u[o + S.z] };
}

let tmp: ImageData | null = null;
/** BGRA32 (top-down) の矩形 [l,t,l+w,t+h) を RGBA ImageData に変換 (alpha=255 固定; tmp を再利用) */
function convert(src: Uint32Array, sw: number, l: number, t: number, w: number, h: number): ImageData {
  if (!tmp || tmp.width !== w || tmp.height !== h) tmp = new ImageData(w, h);
  const dst = new Uint32Array(tmp.data.buffer);
  for (let y = 0; y < h; y++) {
    let si = (t + y) * sw + l, di = y * w;
    for (let x = 0; x < w; x++, si++, di++) {
      const p = src[si];
      // BGRA(LE u32 = 0xAARRGGBB) -> RGBA(LE u32 = 0xAABBGGRR), alpha=255
      dst[di] = 0xff000000 | ((p & 0xff) << 16) | (p & 0xff00) | ((p >>> 16) & 0xff);
    }
  }
  return tmp;
}
/** surface s の client 矩形 [l,t,r,b) を desktop へ描く */
function blit(s: Surf, l: number, t: number, r: number, b: number): void {
  if (!s.state || !s.visible) return;
  l = Math.max(0, l); t = Math.max(0, t); r = Math.min(s.w, r); b = Math.min(s.h, b);
  // desktop クリップ
  l = Math.max(l, -s.x); t = Math.max(t, -s.y); r = Math.min(r, canvasW - s.x); b = Math.min(b, canvasH - s.y);
  const w = r - l, h = b - t;
  if (w <= 0 || h <= 0) return;
  const sw = s.stride >> 2;
  const src = new Uint32Array(refresh().buffer, s.pixels, sw * s.h);
  g2d.putImageData(convert(src, sw, l, t, w, h), s.x + l, s.y + t);
}
function present(id: number, l: number, t: number, r: number, b: number): void {
  const v = refresh();
  const s = surf(v, id);
  blit(s, l, t, r, b);
  // より前面で重なる surface を再描画
  const dl = s.x + l, dt = s.y + t, dr = s.x + r, db = s.y + b;
  for (let i = 0; i < GUI_MAX_SURF; i++) {
    if (i === id) continue;
    const o = surf(v, i);
    if (!o.state || !o.visible || o.z <= s.z) continue;
    const il = Math.max(dl, o.x), it = Math.max(dt, o.y), ir = Math.min(dr, o.x + o.w), ib = Math.min(db, o.y + o.h);
    if (ir > il && ib > it) blit(o, il - o.x, it - o.y, ir - o.x, ib - o.y);
  }
}
function recompose(): void {
  const v = refresh();
  g2d.fillStyle = "#000"; g2d.fillRect(0, 0, canvasW, canvasH);
  const list: Surf[] = [];
  for (let i = 0; i < GUI_MAX_SURF; i++) { const s = surf(v, i); if (s.state) list.push(s); }
  list.sort((a, b) => a.z - b.z);
  for (const s of list) blit(s, 0, 0, s.w, s.h);
}

function title(v: GuiView, id: number): string {
  const o = OFF.surf + id * SURF_WORDS * 4 + S.titleByte;
  let n = 0;
  while (n < 63 && v.u8[o + n]) n++;
  return new TextDecoder().decode(v.u8.slice(o, o + n));
}

function drain(): void {
  let v = refresh();
  for (;;) {
    const head = Atomics.load(v.i32, W.outHead) >>> 0;
    const tail = Atomics.load(v.i32, W.outTail) >>> 0;
    if (head === tail) break;
    const o = (OFF.outRecs >> 2) + (head & (GUI_OUT_RECS - 1)) * 8;
    const r = v.u32.subarray(o, o + 8);
    switch (r[0]) {
      case CMD.SURF_CREATE: case CMD.SURF_DESTROY: case CMD.SURF_CHANGE: recompose(); break;
      case CMD.PRESENT: present(r[1], r[2] | 0, r[3] | 0, r[4] | 0, r[5] | 0); break;
      case CMD.FRAME_END:
        framesDone++;
        Atomics.store(v.i32, W.presentDoneSeq, r[1] | 0);
        Atomics.notify(v.i32, W.presentDoneSeq);
        ctx.postMessage({ type: "frame", seq: r[1] });
        break;
      case CMD.SET_TITLE: ctx.postMessage({ type: "title", surf: r[1], title: title(v, r[1]) }); break;
      case CMD.SET_CURSOR: ctx.postMessage({ type: "cursor", shape: r[2] }); break;
      case CMD.LOG: {
        const n = r[1] & 0xff;
        const bytes = new Uint8Array(v.buffer, v.base + o * 4 + 8, n).slice();
        logAcc += new TextDecoder().decode(bytes);
        if (r[1] & 0x100) { ctx.postMessage({ type: "log", line: logAcc }); logAcc = ""; }
        break;
      }
      case CMD.EXIT: ctx.postMessage({ type: "exit", code: r[1] | 0 }); break;
      default: break;
    }
    Atomics.store(v.i32, W.outHead, (head + 1) | 0);
    Atomics.notify(v.i32, W.outHead);
    v = refresh();
  }
}

type WaitAsync = (ta: Int32Array, index: number, value: number) => { async: boolean; value: Promise<string> | string };
function loop(): void {
  const v = refresh();
  drain();
  const tail = Atomics.load(v.i32, W.outTail);
  const head = Atomics.load(v.i32, W.outHead);
  if (tail !== head) { queueMicrotask(loop); return; }
  const r = (Atomics as unknown as { waitAsync: WaitAsync }).waitAsync(v.i32, W.outTail, tail);
  if (r.async) (r.value as Promise<string>).then(loop);
  else queueMicrotask(loop);
}

/** 描画経路 (変換 + putImageData) の純スループット計測。合成画像を使用 (実 surface には触れない) */
function bench(m: BenchMsg): void {
  const src = new Uint32Array(m.width * m.height);
  for (let i = 0; i < src.length; i++) src[i] = 0xff000000 | (i * 2654435761);
  const oc = new OffscreenCanvas(m.width, m.height);
  const c = oc.getContext("2d", { alpha: false, willReadFrequently: true }) as OffscreenCanvasRenderingContext2D;
  let t0 = performance.now();
  for (let i = 0; i < m.iters; i++) convert(src, m.width, 0, 0, m.width, m.height);
  const tConv = performance.now() - t0;
  t0 = performance.now();
  for (let i = 0; i < m.iters; i++) c.putImageData(convert(src, m.width, 0, 0, m.width, m.height), 0, 0);
  const tAll = performance.now() - t0;
  ctx.postMessage({ type: "bench", id: m.id, width: m.width, height: m.height, iters: m.iters, convertMs: tConv / m.iters, convertPutMs: tAll / m.iters });
}

ctx.onmessage = (ev: MessageEvent<InitMsg | ReadbackMsg | BenchMsg>) => {
  const m = ev.data;
  if (m.type === "init") {
    memory = m.memory; base = m.base; canvasW = m.width; canvasH = m.height;
    view = new GuiView(memory.buffer, base);
    view.check();
    g2d = m.canvas.getContext("2d", { alpha: false, willReadFrequently: true }) as OffscreenCanvasRenderingContext2D;
    g2d.fillStyle = "#000"; g2d.fillRect(0, 0, canvasW, canvasH);
    ctx.postMessage({ type: "ready" });
    loop();
  } else if (m.type === "bench") {
    bench(m);
  } else if (m.type === "readback") {
    const img = g2d.getImageData(0, 0, canvasW, canvasH);
    ctx.postMessage({ type: "readback", id: m.id, width: canvasW, height: canvasH, data: img.data.buffer }, [img.data.buffer]);
  }
};
