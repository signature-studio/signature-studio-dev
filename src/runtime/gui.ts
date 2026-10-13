/**
 * gui.ts — ブラウザ main thread 側の GUI host (tools/gui/PROTOCOL.md)。
 *
 * 役割:
 *  1. 共有領域 (GuiShared) を初期化し host_ready を立てる (wasm 側 shim は host_ready まで待機)
 *  2. <canvas> を OffscreenCanvas に移譲して gui_worker.ts へ渡す (描画は worker 側)
 *  3. DOM 入力 (pointer/wheel/key/focus) を入力リングへ書き、shim の doorbell を鳴らす
 *  4. worker からの通知 (log/frame/title/cursor/exit) を購読可能にする (E2E の同期点にも使う: sleep 不要)
 */
import { CSS_CURSOR, GUI_IN_RECS, GuiView, IN, MOD, OFF, W, vkFromCode } from "./gui_proto.js";

export type GuiHostOptions = {
  canvas: HTMLCanvasElement;
  memory: WebAssembly.Memory;
  /** wasm の gui_shared_ptr() */
  base: number;
  width: number;
  height: number;
  /** gui_worker.js の URL */
  workerUrl: URL | string;
  /** frame 通知ごとに累計フレーム数で呼ばれる (window.__webstudio.frames の更新用) */
  onFrame?: (totalFrames: number) => void;
};

type Waiter<T> = { match: (v: T) => boolean; resolve: (v: T) => void };

export class GuiHost {
  readonly view: GuiView;
  readonly logs: string[] = [];
  frames = 0;
  lastFrameSeq = 0;
  exitCode: number | null = null;
  private readonly worker: Worker;
  private readonly canvas: HTMLCanvasElement;
  private readonly onFrame?: (totalFrames: number) => void;
  private readonly logWaiters: Array<Waiter<string>> = [];
  private readonly frameWaiters: Array<Waiter<number>> = [];
  private readbackId = 0;
  private readonly readbacks = new Map<number, (r: { width: number; height: number; data: Uint8ClampedArray }) => void>();
  private readonly benches = new Map<number, (r: { convertMs: number; convertPutMs: number }) => void>();
  private logCursor = 0;
  private inSeq = 0;
  private exitResolve: ((c: number) => void) | null = null;
  readonly exited = new Promise<number>((res) => { this.exitResolve = res; });

  private constructor(o: GuiHostOptions) {
    this.canvas = o.canvas;
    this.onFrame = o.onFrame;
    this.view = new GuiView(o.memory.buffer, o.base);
    this.worker = new Worker(o.workerUrl, { type: "module" });
  }

  /** 共有領域を初期化し worker を起動、入力を接続する */
  static async attach(o: GuiHostOptions): Promise<GuiHost> {
    const h = new GuiHost(o);
    const v = h.view;
    v.u32[W.magic] = 0; // magic は wasm 側 init_shared() が書く。ここでは screen のみ
    o.canvas.width = o.width; o.canvas.height = o.height;
    const off = o.canvas.transferControlToOffscreen();
    const ready = new Promise<void>((res) => {
      h.worker.addEventListener("message", (ev: MessageEvent) => { if ((ev.data as { type: string }).type === "ready") res(); }, { once: true });
    });
    h.worker.onmessage = (ev: MessageEvent) => h.onWorker(ev.data as WorkerMsg);
    // magic は wasm の gui_sh() が書くまで未定義 => worker init 前に wasm 側 init を待つ必要がある:
    // host_ready を立てると wasm が init_shared を行う。ここで先に立てる前に screen を書く。
    Atomics.store(v.i32, W.screenW, o.width);
    Atomics.store(v.i32, W.screenH, o.height);
    Atomics.store(v.i32, W.dprX100, Math.round((globalThis.devicePixelRatio || 1) * 100));
    Atomics.store(v.i32, W.focused, document.hasFocus() ? 1 : 0);
    Atomics.store(v.i32, W.pageVisible, document.visibilityState === "visible" ? 1 : 0);
    // worker へは magic 検証を遅延するため先に magic/size を host 側が書いておく (wasm 側も同値を書く)
    Atomics.store(v.i32, W.magic, 0x31495547);
    Atomics.store(v.i32, W.version, 1);
    Atomics.store(v.i32, W.totalSize, OFF.total);
    h.worker.postMessage({ type: "init", canvas: off, memory: o.memory, base: o.base, width: o.width, height: o.height }, [off]);
    await ready;
    h.bindInput();
    Atomics.store(v.i32, W.hostReady, 1);
    Atomics.notify(v.i32, W.hostReady);
    return h;
  }

  // ---------------- worker 通知 ----------------
  private onWorker(m: WorkerMsg): void {
    switch (m.type) {
      case "log":
        this.logs.push(m.line);
        for (let i = this.logWaiters.length - 1; i >= 0; i--) {
          const w = this.logWaiters[i];
          if (w.match(m.line)) { this.logWaiters.splice(i, 1); w.resolve(m.line); }
        }
        break;
      case "frame":
        this.frames++; this.lastFrameSeq = m.seq;
        this.onFrame?.(this.frames);
        for (let i = this.frameWaiters.length - 1; i >= 0; i--) {
          const w = this.frameWaiters[i];
          if (w.match(m.seq)) { this.frameWaiters.splice(i, 1); w.resolve(m.seq); }
        }
        break;
      case "title": document.title = m.title; break;
      case "cursor": this.canvas.style.cursor = CSS_CURSOR[m.shape] ?? "default"; break;
      case "exit": this.exitCode = m.code; this.exitResolve?.(m.code); break;
      case "readback": {
        const cb = this.readbacks.get(m.id);
        if (cb) { this.readbacks.delete(m.id); cb({ width: m.width, height: m.height, data: new Uint8ClampedArray(m.data) }); }
        break;
      }
      case "bench": { const cb = this.benches.get(m.id); if (cb) { this.benches.delete(m.id); cb({ convertMs: m.convertMs, convertPutMs: m.convertPutMs }); } break; }
      default: break;
    }
  }
  /** 未消費 LOG から prefix 一致を探し (cursor 以降)、無ければ到着を待つ。見つけたら cursor を進める */
  waitLog(prefix: string): Promise<string> {
    for (let i = this.logCursor; i < this.logs.length; i++) {
      if (this.logs[i].startsWith(prefix)) { this.logCursor = i + 1; return Promise.resolve(this.logs[i]); }
    }
    return new Promise((resolve) => {
      this.logWaiters.push({
        match: (l) => l.startsWith(prefix),
        resolve: (l) => { this.logCursor = this.logs.lastIndexOf(l) + 1; resolve(l); },
      });
    });
  }
  waitFrameAfter(seq: number): Promise<number> {
    if (this.lastFrameSeq > seq) return Promise.resolve(this.lastFrameSeq);
    return new Promise((resolve) => this.frameWaiters.push({ match: (s) => s > seq, resolve }));
  }
  /** 描画経路 (BGRA->RGBA 変換 + putImageData) の ms/frame 計測 (合成画像; worker 側) */
  bench(width: number, height: number, iters: number): Promise<{ convertMs: number; convertPutMs: number }> {
    const id = ++this.readbackId;
    return new Promise((res) => { this.benches.set(id, res); this.worker.postMessage({ type: "bench", id, width, height, iters }); });
  }
  /** desktop の RGBA を描画 worker から読み戻す (テスト用) */
  readback(): Promise<{ width: number; height: number; data: Uint8ClampedArray }> {
    const id = ++this.readbackId;
    return new Promise((res) => { this.readbacks.set(id, res); this.worker.postMessage({ type: "readback", id }); });
  }

  // ---------------- 入力 ----------------
  private pushIn(type: number, surf: number, x: number, y: number, a: number, b: number): void {
    const v = this.view;
    const head = Atomics.load(v.i32, W.inHead) >>> 0;
    const tail = Atomics.load(v.i32, W.inTail) >>> 0;
    if (tail - head >= GUI_IN_RECS) { Atomics.add(v.i32, W.inDropped, 1); return; }
    const o = (OFF.inRecs >> 2) + (tail & (GUI_IN_RECS - 1)) * 8;
    v.i32[o] = type; v.i32[o + 1] = surf; v.i32[o + 2] = x; v.i32[o + 3] = y; v.i32[o + 4] = a; v.i32[o + 5] = b;
    v.i32[o + 6] = Math.round(performance.now()) | 0; v.i32[o + 7] = ++this.inSeq;
    Atomics.store(v.i32, W.inTail, (tail + 1) | 0);
    Atomics.add(v.i32, W.inPushed, 1);
    Atomics.add(v.i32, W.doorbell, 1);
    Atomics.notify(v.i32, W.doorbell);
  }
  private modsOf(e: MouseEvent | KeyboardEvent): number {
    return (e.shiftKey ? MOD.SHIFT : 0) | (e.ctrlKey ? MOD.CTRL : 0) | (e.altKey ? MOD.ALT : 0) | (e.metaKey ? MOD.META : 0);
  }
  private pos(e: MouseEvent): [number, number] {
    const r = this.canvas.getBoundingClientRect();
    return [Math.round((e.clientX - r.left) * (this.canvas.width / r.width)), Math.round((e.clientY - r.top) * (this.canvas.height / r.height))];
  }
  private setPointerState(x: number, y: number, e: MouseEvent): void {
    const v = this.view;
    Atomics.store(v.i32, W.cursorX, x); Atomics.store(v.i32, W.cursorY, y);
    let b = 0; if (e.buttons & 1) b |= 1; if (e.buttons & 2) b |= 2; if (e.buttons & 4) b |= 4;
    Atomics.store(v.i32, W.buttons, b);
    Atomics.store(v.i32, W.mods, this.modsOf(e));
  }
  private bindInput(): void {
    const c = this.canvas;
    c.addEventListener("pointermove", (e) => { const [x, y] = this.pos(e); this.setPointerState(x, y, e); this.pushIn(IN.MOUSE_MOVE, 0, x, y, this.view.i32[W.buttons], 0); });
    c.addEventListener("pointerdown", (e) => {
      c.setPointerCapture(e.pointerId); c.focus?.();
      const [x, y] = this.pos(e); this.setPointerState(x, y, e); this.pushIn(IN.MOUSE_DOWN, 0, x, y, e.button, this.modsOf(e));
    });
    c.addEventListener("pointerup", (e) => { const [x, y] = this.pos(e); this.setPointerState(x, y, e); this.pushIn(IN.MOUSE_UP, 0, x, y, e.button, this.modsOf(e)); });
    c.addEventListener("wheel", (e) => {
      e.preventDefault(); const [x, y] = this.pos(e);
      const unit = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? 400 : 100;
      this.pushIn(IN.WHEEL, 0, x, y, Math.round((-e.deltaY / unit) * 120) | 0, this.modsOf(e));
    }, { passive: false });
    c.addEventListener("contextmenu", (e) => e.preventDefault());
    c.tabIndex = 0;
    const key = (down: boolean) => (e: KeyboardEvent) => {
      const vk = vkFromCode(e.code);
      if (!vk) return;
      e.preventDefault();
      const v = this.view, w = W.keyDown + (vk >> 5);
      if (down) Atomics.or(v.i32, w, 1 << (vk & 31)); else Atomics.and(v.i32, w, ~(1 << (vk & 31)));
      Atomics.store(v.i32, W.mods, this.modsOf(e));
      const flags = (e.repeat ? 1 : 0) | (this.modsOf(e) << 16);
      this.pushIn(down ? IN.KEY_DOWN : IN.KEY_UP, 0, 0, 0, vk, flags);
      if (down) {
        let ch = 0;
        if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) ch = e.key.charCodeAt(0);
        else if (e.key === "Enter") ch = 13; else if (e.key === "Backspace") ch = 8; else if (e.key === "Tab") ch = 9; else if (e.key === "Escape") ch = 27;
        if (ch) this.pushIn(IN.CHAR, 0, 0, 0, ch, 0);
      }
    };
    window.addEventListener("keydown", key(true));
    window.addEventListener("keyup", key(false));
    window.addEventListener("focus", () => { Atomics.store(this.view.i32, W.focused, 1); this.pushIn(IN.FOCUS, 0, 0, 0, 1, 0); });
    window.addEventListener("blur", () => { Atomics.store(this.view.i32, W.focused, 0); this.pushIn(IN.FOCUS, 0, 0, 0, 0, 0); });
  }
}

type WorkerMsg =
  | { type: "ready" }
  | { type: "log"; line: string }
  | { type: "frame"; seq: number }
  | { type: "title"; surf: number; title: string }
  | { type: "cursor"; shape: number }
  | { type: "exit"; code: number }
  | { type: "readback"; id: number; width: number; height: number; data: ArrayBuffer }
  | { type: "bench"; id: number; width: number; height: number; iters: number; convertMs: number; convertPutMs: number };
