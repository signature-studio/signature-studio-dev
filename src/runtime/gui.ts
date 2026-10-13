/**
 * gui.ts — ブラウザ main thread 側の GUI host (tools/gui/PROTOCOL.md)。
 *
 * 役割:
 *  1. 共有領域 (GuiShared) を初期化し host_ready を立てる (wasm 側 shim は host_ready まで待機)
 *  2. <canvas> を OffscreenCanvas に移譲して gui_worker.ts へ渡す (描画は worker 側)
 *  3. DOM 入力 (pointer/wheel/key/focus) を入力リングへ書き、shim の doorbell を鳴らす
 *  4. worker からの通知 (log/frame/title/cursor/exit) を購読可能にする (E2E の同期点にも使う: sleep 不要)
 */
import type { GuiPresentOptions, GuiRenderStats } from "./gui_renderer.js";
import { CSS_CURSOR, GUI_IN_RECS, GuiView, IN, MOD, OFF, SCAN_BY_CODE, W, vkFromCode } from "./gui_proto.js";

/** KeyboardLayoutMap (Keyboard API) から配列を推定: 物理 KeyQ/KeyY の文字で US(0x0409)/DE(0x0407)/FR(0x040C)。判定不能は US */
export function layoutFromMap(get: (code: string) => string | undefined): number {
  const q = get("KeyQ"), y = get("KeyY");
  if (q === "a") return 0x040c;
  if (y === "z") return 0x0407;
  return 0x0409;
}

/** IME 文字列を GUI_IN_IME レコード列へ分割 (1 レコード = 最大 4 UTF-16)。a = phase | n<<8 | first<<12 | last<<13、x = u0|u1<<16、y = u2|u3<<16、b = cursor */
export function imeRecords(phase: number, text: string, cursor: number): Array<{ x: number; y: number; a: number; b: number }> {
  const out: Array<{ x: number; y: number; a: number; b: number }> = [];
  const n = Math.min(text.length, 508);
  let off = 0;
  do {
    const k = Math.min(4, n - off);
    const u = [0, 0, 0, 0];
    for (let i = 0; i < k; i++) u[i] = text.charCodeAt(off + i);
    const last = off + k >= n;
    out.push({ x: (u[0] | (u[1] << 16)) | 0, y: (u[2] | (u[3] << 16)) | 0, a: phase | (k << 8) | (off === 0 ? 1 << 12 : 0) | (last ? 1 << 13 : 0), b: cursor });
    off += k;
  } while (off < n);
  return out;
}

export type GuiHostOptions = {
  canvas: HTMLCanvasElement;
  memory: WebAssembly.Memory;
  /** wasm の gui_shared_ptr() */
  base: number;
  width: number;
  height: number;
  /** gui_worker.js の URL (worker 未指定時) */
  workerUrl?: URL | string;
  /** 呼び出し側で生成済みの描画 Worker (バンドラが Worker チャンクを作れるよう `new Worker(new URL(..., import.meta.url))` を呼び出し側に置く場合) */
  worker?: Worker;
  /** frame 通知ごとに累計フレーム数で呼ばれる (window.__webstudio.frames の更新用) */
  onFrame?: (totalFrames: number) => void;
  /** present 方式 (backend / sync / seqlock / upload)。未指定 = 従来の 2D + putImageData */
  present?: GuiPresentOptions;
};

export type GuiPresentInfo = { backend: "2d" | "webgl2"; sync: "immediate" | "raf"; seqlock: boolean; upload: string };

type Waiter<T> = { match: (v: T) => boolean; resolve: (v: T) => void };

export class GuiHost {
  readonly view: GuiView;
  readonly logs: string[] = [];
  frames = 0;
  lastFrameSeq = 0;
  exitCode: number | null = null;
  /** 描画 worker が実際に採用した present 方式 (attach 完了後に有効) */
  presentInfo: GuiPresentInfo | null = null;
  private readonly worker: Worker;
  private readonly canvas: HTMLCanvasElement;
  private readonly onFrame?: (totalFrames: number) => void;
  private readonly logWaiters: Array<Waiter<string>> = [];
  private readonly frameWaiters: Array<Waiter<number>> = [];
  private readbackId = 0;
  private readonly readbacks = new Map<number, (r: { width: number; height: number; data: Uint8ClampedArray }) => void>();
  private readonly statsWaiters = new Map<number, (r: GuiStatsReply) => void>();
  private readonly benches = new Map<number, (r: { convertMs: number; convertPutMs: number }) => void>();
  private logCursor = 0;
  private inSeq = 0;
  /** GUI-6: Pointer Lock 状態 (host が相対量を積算して cursor_x/y へ書く) */
  locked = false;
  lockRequests = 0;
  private clip: [number, number, number, number] | null = null;
  readonly ime: HTMLTextAreaElement;
  private composing = false;
  imeAt: [number, number] | null = null;
  private exitResolve: ((c: number) => void) | null = null;
  readonly exited = new Promise<number>((res) => { this.exitResolve = res; });

  private constructor(o: GuiHostOptions) {
    this.canvas = o.canvas;
    this.ime = document.createElement("textarea");
    this.ime.setAttribute("aria-hidden", "true");
    this.ime.style.cssText = "position:absolute;opacity:0;width:1px;height:1px;left:0;top:0;pointer-events:none;border:0;padding:0";
    o.canvas.parentElement?.appendChild(this.ime);
    this.onFrame = o.onFrame;
    this.view = new GuiView(o.memory.buffer, o.base);
    if (!o.worker && !o.workerUrl) throw new Error("[gui] worker か workerUrl が必要");
    this.worker = o.worker ?? new Worker(o.workerUrl as URL | string, { type: "module" });
  }

  /** 共有領域を初期化し worker を起動、入力を接続する */
  static async attach(o: GuiHostOptions): Promise<GuiHost> {
    const h = new GuiHost(o);
    const v = h.view;
    v.u32[W.magic] = 0; // magic は wasm 側 init_shared() が書く。ここでは screen のみ
    o.canvas.width = o.width; o.canvas.height = o.height;
    const off = o.canvas.transferControlToOffscreen();
    const ready = new Promise<void>((res) => {
      h.worker.addEventListener("message", (ev: MessageEvent) => {
        const m = ev.data as { type: string; info?: GuiPresentInfo };
        if (m.type === "ready") { h.presentInfo = m.info ?? null; res(); }
      }, { once: true });
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
    h.worker.postMessage({ type: "init", canvas: off, memory: o.memory, base: o.base, width: o.width, height: o.height, present: o.present }, [off]);
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
      case "ptrlock": if (m.on) { this.lockRequests++; void Promise.resolve(this.canvas.requestPointerLock?.()).catch(() => {}); } else if (document.pointerLockElement === this.canvas) document.exitPointerLock(); break;
      case "imepos": this.imeAt = [m.x, m.y]; this.ime.style.left = `${m.x}px`; this.ime.style.top = `${m.y}px`; break;
      case "cliprect": this.clip = m.r > m.l && m.b > m.t ? [m.l, m.t, m.r, m.b] : null; break;
      case "touchwin": this.canvas.style.touchAction = m.n > 0 ? "none" : "auto"; break;
      case "exit": this.exitCode = m.code; this.exitResolve?.(m.code); break;
      case "readback": {
        const cb = this.readbacks.get(m.id);
        if (cb) { this.readbacks.delete(m.id); cb({ width: m.width, height: m.height, data: new Uint8ClampedArray(m.data) }); }
        break;
      }
      case "stats": { const cb = this.statsWaiters.get(m.id); if (cb) { this.statsWaiters.delete(m.id); cb({ stats: m.stats, gl: m.gl, frames: m.frames }); } break; }
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
  /** 描画 worker の present 統計 (flush 回数・併合後矩形数・seqlock 持ち越し数など) */
  stats(): Promise<GuiStatsReply> {
    const id = ++this.readbackId;
    return new Promise((res) => { this.statsWaiters.set(id, res); this.worker.postMessage({ type: "stats", id }); });
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
  /** Pointer Lock 中の仮想カーソル: shim の SetCursorPos (shared cursor_x/y) を基点に movement を積算し、ClipCursor 矩形 (無ければ画面) へ clamp */
  private lockedMove(e: PointerEvent): [number, number] {
    const v = this.view, sw = Atomics.load(v.i32, W.screenW), sh = Atomics.load(v.i32, W.screenH);
    const [l, t, r, b] = this.clip ?? [0, 0, sw, sh];
    const x = Math.max(l, Math.min(r - 1, Atomics.load(v.i32, W.cursorX) + Math.round(e.movementX * (this.canvas.width / this.canvas.getBoundingClientRect().width))));
    const y = Math.max(t, Math.min(b - 1, Atomics.load(v.i32, W.cursorY) + Math.round(e.movementY * (this.canvas.height / this.canvas.getBoundingClientRect().height))));
    return [x, y];
  }
  private sendLayout(code: number): void { this.pushIn(IN.LAYOUT, 0, 0, 0, code, 0); }
  private bindInput(): void {
    const c = this.canvas;
    c.addEventListener("pointermove", (e) => {
      if (e.pointerType === "touch") { const [x, y] = this.pos(e); this.pushIn(IN.TOUCH, 0, x, y, (e.pointerId & 0xff) | (1 << 8) | (e.isPrimary ? 1 << 12 : 0), (Math.round(e.width) & 0xffff) | ((Math.round(e.height) & 0xffff) << 16)); return; }
      const [x, y] = this.locked ? this.lockedMove(e) : this.pos(e);
      this.setPointerState(x, y, e); this.pushIn(IN.MOUSE_MOVE, 0, x, y, this.view.i32[W.buttons], 0);
    });
    c.addEventListener("pointerdown", (e) => {
      c.setPointerCapture(e.pointerId); c.focus?.();
      const [x, y] = this.pos(e);
      if (e.pointerType === "touch") { this.pushIn(IN.TOUCH, 0, x, y, (e.pointerId & 0xff) | (e.isPrimary ? 1 << 12 : 0), (Math.round(e.width) & 0xffff) | ((Math.round(e.height) & 0xffff) << 16)); return; }
      this.setPointerState(x, y, e); this.pushIn(IN.MOUSE_DOWN, 0, x, y, e.button, this.modsOf(e));
    });
    const up = (cancel: boolean) => (e: PointerEvent) => {
      const [x, y] = this.pos(e);
      if (e.pointerType === "touch") { this.pushIn(IN.TOUCH, 0, x, y, (e.pointerId & 0xff) | ((cancel ? 3 : 2) << 8) | (e.isPrimary ? 1 << 12 : 0), 0); return; }
      if (cancel) return;
      const [mx, my] = this.locked ? [Atomics.load(this.view.i32, W.cursorX), Atomics.load(this.view.i32, W.cursorY)] : [x, y];
      this.setPointerState(mx, my, e); this.pushIn(IN.MOUSE_UP, 0, mx, my, e.button, this.modsOf(e));
    };
    c.addEventListener("pointerup", up(false));
    c.addEventListener("pointercancel", up(true));
    document.addEventListener("pointerlockchange", () => {
      this.locked = document.pointerLockElement === c;
      this.pushIn(IN.POINTER_LOCK, 0, 0, 0, this.locked ? 1 : 0, 0);
    });
    c.addEventListener("wheel", (e) => {
      e.preventDefault(); const [x, y] = this.pos(e);
      const unit = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? 400 : 100;
      this.pushIn(IN.WHEEL, 0, x, y, Math.round((-e.deltaY / unit) * 120) | 0, this.modsOf(e));
    }, { passive: false });
    c.addEventListener("contextmenu", (e) => e.preventDefault());
    c.tabIndex = 0;
    const key = (down: boolean) => (e: KeyboardEvent) => {
      if (e.isComposing || e.keyCode === 229) return;   // IME 変換中のキーは composition イベントへ任せる
      const vk = vkFromCode(e.code);
      if (!vk) return;
      e.preventDefault();
      const v = this.view, w = W.keyDown + (vk >> 5);
      if (down) Atomics.or(v.i32, w, 1 << (vk & 31)); else Atomics.and(v.i32, w, ~(1 << (vk & 31)));
      Atomics.store(v.i32, W.mods, this.modsOf(e));
      const sc = SCAN_BY_CODE[e.code] ?? [0, 0];
      const flags = (e.repeat ? 1 : 0) | (sc[1] ? 2 : 0) | (sc[0] << 8) | (this.modsOf(e) << 16);
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
    // IME: 隠し textarea の composition イベント → GUI_IN_IME。確定文字列は WM_IME_COMPOSITION(GCS_RESULTSTR) として届き、WM_CHAR は composition 中の入力では生成しない
    const send = (phase: number, text: string, cursor: number) => { for (const r of imeRecords(phase, text, cursor)) this.pushIn(IN.IME, 0, r.x, r.y, r.a, r.b); };
    this.ime.addEventListener("compositionstart", () => { this.composing = true; send(1, "", 0); });
    this.ime.addEventListener("compositionupdate", (e) => { send(2, e.data, e.data.length); });
    this.ime.addEventListener("compositionend", (e) => { this.composing = false; send(e.data ? 3 : 4, e.data, 0); this.ime.value = ""; });
    c.addEventListener("focus", () => { this.ime.focus({ preventScroll: true }); });
    // キー配列: Keyboard API (Chromium) の KeyboardLayoutMap から推定して shim へ通知 (取得不能なら US のまま)
    const kb = (navigator as unknown as { keyboard?: { getLayoutMap?: () => Promise<{ get(k: string): string | undefined }>; addEventListener?: (t: string, f: () => void) => void } }).keyboard;
    const detect = () => { void kb?.getLayoutMap?.().then((m) => this.sendLayout(layoutFromMap((k) => m.get(k)))).catch(() => {}); };
    detect(); kb?.addEventListener?.("layoutchange", detect);
  }
  /** 現在 IME composition 中か (e2e 用) */
  get isComposing(): boolean { return this.composing; }
  /** layout を明示設定 (e2e / 設定 UI 用) */
  setLayout(langid: number): void { this.sendLayout(langid); }
}

export type GuiStatsReply = { stats: GuiRenderStats; gl: { uploads: number; uploadPixels: number; draws: number; directFallbacks: number; contextRestores: number } | null; frames: number };

type WorkerMsg =
  | { type: "ready"; info?: GuiPresentInfo }
  | { type: "stats"; id: number; stats: GuiRenderStats; gl: GuiStatsReply["gl"]; frames: number }
  | { type: "log"; line: string }
  | { type: "frame"; seq: number }
  | { type: "title"; surf: number; title: string }
  | { type: "cursor"; shape: number }
  | { type: "ptrlock"; on: boolean }
  | { type: "imepos"; surf: number; x: number; y: number }
  | { type: "cliprect"; l: number; t: number; r: number; b: number }
  | { type: "touchwin"; n: number }
  | { type: "exit"; code: number }
  | { type: "readback"; id: number; width: number; height: number; data: ArrayBuffer }
  | { type: "bench"; id: number; width: number; height: number; iters: number; convertMs: number; convertPutMs: number };
