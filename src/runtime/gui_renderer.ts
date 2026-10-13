/**
 * gui_renderer.ts — GuiShared の out ring を消費して OffscreenCanvas(2D) へ合成する描画器 (Worker 非依存)。
 *
 * gui_worker.ts (専用描画 Worker) と fl-runtime Worker (worker.ts の gui-attach) の双方から使う。
 * 呼び出し側は「Atomics.wait でブロックしていない Worker」で動かすこと (待機は Atomics.waitAsync)。
 *
 * - 共有領域は wasm の WebAssembly.Memory 上 (SAB)。メモリ成長に追従するため呼出ごとに memory.buffer を取り直す。
 * - surface ピクセルは BGRA32 top-down。dirty 矩形のみ RGBA へ変換して putImageData (alpha は 255 に固定)。
 * - z-order: 描画した矩形に重なるより前面の surface を再描画して前後関係を保つ。
 */
import { CMD, GUI_MAX_SURF, GUI_OUT_RECS, GuiView, OFF, S, SURF_WORDS, W } from "./gui_proto.js";

export type GuiRenderMsg =
  | { type: "log"; line: string }
  | { type: "frame"; seq: number }
  | { type: "title"; surf: number; title: string }
  | { type: "cursor"; shape: number }
  | { type: "exit"; code: number };

export type GuiRendererOptions = {
  canvas: OffscreenCanvas;
  memory: WebAssembly.Memory;
  /** wasm の gui_shared_ptr() */
  base: number;
  width: number;
  height: number;
  post: (m: GuiRenderMsg) => void;
};

type Surf = { id: number; state: number; visible: number; x: number; y: number; w: number; h: number; stride: number; pixels: number; z: number };

type WaitAsync = (ta: Int32Array, index: number, value: number) => { async: boolean; value: Promise<string> | string };

export class GuiRenderer {
  framesDone = 0;
  private view: GuiView;
  private readonly g2d: OffscreenCanvasRenderingContext2D;
  private readonly memory: WebAssembly.Memory;
  private readonly base: number;
  private readonly canvasW: number;
  private readonly canvasH: number;
  private readonly post: (m: GuiRenderMsg) => void;
  private logAcc = "";
  private tmp: ImageData | null = null;
  private stopped = false;

  constructor(o: GuiRendererOptions) {
    this.memory = o.memory;
    this.base = o.base;
    this.canvasW = o.width;
    this.canvasH = o.height;
    this.post = o.post;
    this.view = new GuiView(this.memory.buffer, this.base);
    this.view.check();
    this.g2d = o.canvas.getContext("2d", { alpha: false, willReadFrequently: true }) as OffscreenCanvasRenderingContext2D;
    this.g2d.fillStyle = "#000";
    this.g2d.fillRect(0, 0, this.canvasW, this.canvasH);
  }

  /** out ring の消費ループを開始 (イベント駆動, ポーリング無し) */
  start(): void {
    this.loop();
  }

  stop(): void {
    this.stopped = true;
  }

  /** desktop の RGBA を読み戻す (テスト用) */
  readback(): { width: number; height: number; data: ArrayBuffer } {
    const img = this.g2d.getImageData(0, 0, this.canvasW, this.canvasH);
    return { width: this.canvasW, height: this.canvasH, data: img.data.buffer as ArrayBuffer };
  }

  /** 描画経路 (変換 + putImageData) の純スループット計測。合成画像を使用 (実 surface には触れない) */
  bench(width: number, height: number, iters: number): { convertMs: number; convertPutMs: number } {
    const src = new Uint32Array(width * height);
    for (let i = 0; i < src.length; i++) src[i] = 0xff000000 | (i * 2654435761);
    const oc = new OffscreenCanvas(width, height);
    const c = oc.getContext("2d", { alpha: false, willReadFrequently: true }) as OffscreenCanvasRenderingContext2D;
    let t0 = performance.now();
    for (let i = 0; i < iters; i++) this.convert(src, width, 0, 0, width, height);
    const tConv = performance.now() - t0;
    t0 = performance.now();
    for (let i = 0; i < iters; i++) c.putImageData(this.convert(src, width, 0, 0, width, height), 0, 0);
    const tAll = performance.now() - t0;
    return { convertMs: tConv / iters, convertPutMs: tAll / iters };
  }

  private refresh(): GuiView {
    if (this.view.buffer !== this.memory.buffer) this.view = new GuiView(this.memory.buffer, this.base);
    return this.view;
  }

  private surf(v: GuiView, id: number): Surf {
    const o = (OFF.surf >> 2) + id * SURF_WORDS;
    const u = v.u32, i = v.i32;
    return { id, state: Atomics.load(i, o + S.state), visible: u[o + S.visible], x: i[o + S.x], y: i[o + S.y], w: u[o + S.w], h: u[o + S.h],
             stride: u[o + S.stride], pixels: u[o + S.pixels], z: u[o + S.z] };
  }

  /** BGRA32 (top-down) の矩形 [l,t,l+w,t+h) を RGBA ImageData に変換 (alpha=255 固定; tmp を再利用) */
  private convert(src: Uint32Array, sw: number, l: number, t: number, w: number, h: number): ImageData {
    if (!this.tmp || this.tmp.width !== w || this.tmp.height !== h) this.tmp = new ImageData(w, h);
    const dst = new Uint32Array(this.tmp.data.buffer);
    for (let y = 0; y < h; y++) {
      let si = (t + y) * sw + l, di = y * w;
      for (let x = 0; x < w; x++, si++, di++) {
        const p = src[si];
        // BGRA(LE u32 = 0xAARRGGBB) -> RGBA(LE u32 = 0xAABBGGRR), alpha=255
        dst[di] = 0xff000000 | ((p & 0xff) << 16) | (p & 0xff00) | ((p >>> 16) & 0xff);
      }
    }
    return this.tmp;
  }

  /** surface s の client 矩形 [l,t,r,b) を desktop へ描く */
  private blit(s: Surf, l: number, t: number, r: number, b: number): void {
    if (!s.state || !s.visible) return;
    l = Math.max(0, l); t = Math.max(0, t); r = Math.min(s.w, r); b = Math.min(s.h, b);
    l = Math.max(l, -s.x); t = Math.max(t, -s.y); r = Math.min(r, this.canvasW - s.x); b = Math.min(b, this.canvasH - s.y);
    const w = r - l, h = b - t;
    if (w <= 0 || h <= 0) return;
    const sw = s.stride >> 2;
    const src = new Uint32Array(this.refresh().buffer, s.pixels, sw * s.h);
    this.g2d.putImageData(this.convert(src, sw, l, t, w, h), s.x + l, s.y + t);
  }

  private present(id: number, l: number, t: number, r: number, b: number): void {
    const v = this.refresh();
    const s = this.surf(v, id);
    this.blit(s, l, t, r, b);
    const dl = s.x + l, dt = s.y + t, dr = s.x + r, db = s.y + b;
    for (let i = 0; i < GUI_MAX_SURF; i++) {
      if (i === id) continue;
      const o = this.surf(v, i);
      if (!o.state || !o.visible || o.z <= s.z) continue;
      const il = Math.max(dl, o.x), it = Math.max(dt, o.y), ir = Math.min(dr, o.x + o.w), ib = Math.min(db, o.y + o.h);
      if (ir > il && ib > it) this.blit(o, il - o.x, it - o.y, ir - o.x, ib - o.y);
    }
  }

  private recompose(): void {
    const v = this.refresh();
    this.g2d.fillStyle = "#000";
    this.g2d.fillRect(0, 0, this.canvasW, this.canvasH);
    const list: Surf[] = [];
    for (let i = 0; i < GUI_MAX_SURF; i++) { const s = this.surf(v, i); if (s.state) list.push(s); }
    list.sort((a, b) => a.z - b.z);
    for (const s of list) this.blit(s, 0, 0, s.w, s.h);
  }

  private title(v: GuiView, id: number): string {
    const o = OFF.surf + id * SURF_WORDS * 4 + S.titleByte;
    let n = 0;
    while (n < 63 && v.u8[o + n]) n++;
    return new TextDecoder().decode(v.u8.slice(o, o + n));
  }

  private drain(): void {
    let v = this.refresh();
    for (;;) {
      const head = Atomics.load(v.i32, W.outHead) >>> 0;
      const tail = Atomics.load(v.i32, W.outTail) >>> 0;
      if (head === tail) break;
      const o = (OFF.outRecs >> 2) + (head & (GUI_OUT_RECS - 1)) * 8;
      const r = v.u32.subarray(o, o + 8);
      switch (r[0]) {
        case CMD.SURF_CREATE: case CMD.SURF_DESTROY: case CMD.SURF_CHANGE: this.recompose(); break;
        case CMD.PRESENT: this.present(r[1], r[2] | 0, r[3] | 0, r[4] | 0, r[5] | 0); break;
        case CMD.FRAME_END:
          this.framesDone++;
          Atomics.store(v.i32, W.presentDoneSeq, r[1] | 0);
          Atomics.notify(v.i32, W.presentDoneSeq);
          this.post({ type: "frame", seq: r[1] });
          break;
        case CMD.SET_TITLE: this.post({ type: "title", surf: r[1], title: this.title(v, r[1]) }); break;
        case CMD.SET_CURSOR: this.post({ type: "cursor", shape: r[2] }); break;
        case CMD.LOG: {
          const n = r[1] & 0xff;
          const bytes = new Uint8Array(v.buffer, v.base + o * 4 + 8, n).slice();
          this.logAcc += new TextDecoder().decode(bytes);
          if (r[1] & 0x100) { this.post({ type: "log", line: this.logAcc }); this.logAcc = ""; }
          break;
        }
        case CMD.EXIT: this.post({ type: "exit", code: r[1] | 0 }); break;
        default: break;
      }
      Atomics.store(v.i32, W.outHead, (head + 1) | 0);
      Atomics.notify(v.i32, W.outHead);
      v = this.refresh();
    }
  }

  private loop = (): void => {
    if (this.stopped) return;
    const v = this.refresh();
    this.drain();
    const tail = Atomics.load(v.i32, W.outTail);
    const head = Atomics.load(v.i32, W.outHead);
    if (tail !== head) { queueMicrotask(this.loop); return; }
    const r = (Atomics as unknown as { waitAsync: WaitAsync }).waitAsync(v.i32, W.outTail, tail);
    if (r.async) (r.value as Promise<string>).then(this.loop);
    else queueMicrotask(this.loop);
  };
}
