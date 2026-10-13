/**
 * gui_renderer.ts — GuiShared の out ring を消費して OffscreenCanvas へ合成する描画器 (Worker 非依存)。
 *
 * gui_worker.ts (専用描画 Worker) と fl-runtime Worker (worker.ts の gui-attach) の双方から使う。
 * 呼び出し側は「Atomics.wait でブロックしていない Worker」で動かすこと (待機は Atomics.waitAsync)。
 *
 * - 共有領域は wasm の WebAssembly.Memory 上 (SAB)。メモリ成長に追従するため呼出ごとに memory.buffer を取り直す。
 * - surface ピクセルは BGRA32 top-down。dirty 矩形のみ転送し alpha は 255 に固定。
 * - z-order: 描画した矩形に重なるより前面の surface を再描画して前後関係を保つ。
 *
 * present 方式 (`GuiRendererOptions.present`; 既定 = 従来経路 "2d" + "immediate" で挙動不変):
 * - backend "2d": CPU で BGRA→RGBA 変換 + putImageData / "webgl2": gui_present_gl.ts (texSubImage2D + fragment swizzle) /
 *   "auto": WebGL2 を試し、不可なら "2d"。
 * - sync "immediate": FRAME_END で即時に描画・ack / "raf": FRAME_END を requestAnimationFrame に同期して 1 回にまとめて描画・ack
 *   (rAF が来ない場合は rafTimeoutMs のタイマで描画する)。
 * - dirty 複数矩形: 1 フレーム内の PRESENT を surface ごとに併合 (gui_dirty.ts) して転送。
 * - seqlock: surface の wseq (奇数 = guest が書込み中) を読出し前後で検証。不整合なら矩形を持ち越して 4 ms 後に再試行
 *   (staleMs 以上ずっと読めない場合のみ強制的に読む = 飢餓回避; stats.seqForced)。
 */
import { CMD, GUI_MAX_SURF, GUI_OUT_RECS, GuiView, OFF, S, SURF_WORDS, W } from "./gui_proto.js";
import { type DirtyRect, mergeRects, rectArea } from "./gui_dirty.js";
import { GlPresenter } from "./gui_present_gl.js";

export type GuiRenderMsg =
  | { type: "log"; line: string }
  | { type: "frame"; seq: number }
  | { type: "title"; surf: number; title: string }
  | { type: "cursor"; shape: number }
  | { type: "exit"; code: number };

export type GuiPresentOptions = {
  backend?: "2d" | "webgl2" | "auto";
  sync?: "immediate" | "raf";
  seqlock?: boolean;
  /** webgl2 の転送方式 (既定 auto: 共有メモリ view の直接転送を試し、拒否されたら staged) */
  upload?: "auto" | "direct" | "staged";
  /** raf 同期でフレームが来ない/pending を残したときの救済タイマ (ms) */
  rafTimeoutMs?: number;
  /** seqlock: guest が書込み中のまま連続してこの時間 (ms) を超えて読めない surface は、整合を諦めて強制的に読む (飢餓回避; stats.seqForced) */
  staleMs?: number;
};

export type GuiRendererOptions = {
  canvas: OffscreenCanvas;
  memory: WebAssembly.Memory;
  /** wasm の gui_shared_ptr() */
  base: number;
  width: number;
  height: number;
  post: (m: GuiRenderMsg) => void;
  present?: GuiPresentOptions;
  /** flush (描画) 完了ごと・ack 直前に呼ばれる (テスト/計測用) */
  onFlush?: (r: GuiRenderer) => void;
};

export type GuiRenderStats = {
  /** 描画した flush 回数 / FRAME_END 受信数 / flush 内で処理した PRESENT 数 (併合前) と併合後の矩形数・面積 */
  flushes: number; frameEnds: number; presents: number; rects: number; rectPixels: number;
  rafFlushes: number; timerFlushes: number; immediateFlushes: number; fullRecomposes: number;
  seqRetries: number; seqDeferred: number; seqForced: number;
  flushMs: number; lastFlushMs: number; maxFlushMs: number;
};

type Surf = { id: number; state: number; visible: number; x: number; y: number; w: number; h: number; stride: number; pixels: number; z: number };

type WaitAsync = (ta: Int32Array, index: number, value: number) => { async: boolean; value: Promise<string> | string };

export class GuiRenderer {
  framesDone = 0;
  readonly backend: "2d" | "webgl2";
  readonly sync: "immediate" | "raf";
  readonly seqlock: boolean;
  readonly stats: GuiRenderStats = {
    flushes: 0, frameEnds: 0, presents: 0, rects: 0, rectPixels: 0, rafFlushes: 0, timerFlushes: 0, immediateFlushes: 0, fullRecomposes: 0,
    seqRetries: 0, seqDeferred: 0, seqForced: 0, flushMs: 0, lastFlushMs: 0, maxFlushMs: 0,
  };
  private view: GuiView;
  private readonly g2d: OffscreenCanvasRenderingContext2D | null = null;
  private readonly glp: GlPresenter | null = null;
  private readonly memory: WebAssembly.Memory;
  private readonly base: number;
  private readonly canvasW: number;
  private readonly canvasH: number;
  private readonly post: (m: GuiRenderMsg) => void;
  private readonly onFlush?: (r: GuiRenderer) => void;
  private readonly rafTimeoutMs: number;
  private logAcc = "";
  private tmp: ImageData | null = null;
  private stopped = false;
  /** immediate/raf/seqlock/webgl2 のいずれかなら true (フレーム単位で遅延描画する経路) */
  private readonly deferred: boolean;
  private pending: DirtyRect[] = [];
  private carry: DirtyRect[] = [];
  private needRecompose = false;
  private needFlush = false;
  private drawRects: DirtyRect[] = [];
  private drawAll = false;
  private ingestMs = 0;
  private legacyMs = 0;
  private wdId: ReturnType<typeof setTimeout> | 0 = 0;
  private hasAck = false;
  private ackSeq = 0;
  private rafId = 0;
  private timerId: ReturnType<typeof setTimeout> | 0 = 0;
  private readonly deferSince = new Float64Array(GUI_MAX_SURF);
  private readonly staleMs: number;

  constructor(o: GuiRendererOptions) {
    this.memory = o.memory;
    this.base = o.base;
    this.canvasW = o.width;
    this.canvasH = o.height;
    this.post = o.post;
    this.onFlush = o.onFlush;
    const p = o.present ?? {};
    this.sync = p.sync ?? "immediate";
    this.seqlock = p.seqlock ?? false;
    this.rafTimeoutMs = p.rafTimeoutMs ?? 100;
    this.staleMs = p.staleMs ?? 100;
    this.view = new GuiView(this.memory.buffer, this.base);
    this.view.check();
    const want = p.backend ?? "2d";
    if (want !== "2d") {
      try {
        this.glp = new GlPresenter(o.canvas, o.width, o.height, p.upload ?? "auto");
        this.glp.onRestore = () => { this.needRecompose = true; this.armRetry(0); };
      } catch (e) {
        if (want === "webgl2") throw e;
      }
    }
    if (this.glp) {
      this.backend = "webgl2";
    } else {
      this.backend = "2d";
      this.g2d = o.canvas.getContext("2d", { alpha: false, willReadFrequently: true }) as OffscreenCanvasRenderingContext2D;
      this.g2d.fillStyle = "#000";
      this.g2d.fillRect(0, 0, this.canvasW, this.canvasH);
    }
    this.deferred = this.backend !== "2d" || this.sync !== "immediate" || this.seqlock;
  }

  /** 実際に採用された present 方式 (ready 通知用) */
  info(): { backend: "2d" | "webgl2"; sync: "immediate" | "raf"; seqlock: boolean; upload: string } {
    return { backend: this.backend, sync: this.sync, seqlock: this.seqlock, upload: this.glp ? this.glp.uploadMode : "n/a" };
  }

  glStats(): GlPresenter["stats"] | null {
    return this.glp ? this.glp.stats : null;
  }

  /** GPU の完了まで待つ (webgl2 のみ; 計測用。2d は何もしない) */
  syncGpu(): void {
    this.glp?.sync();
  }

  /** out ring の消費ループを開始 (イベント駆動, ポーリング無し) */
  start(): void {
    this.loop();
  }

  stop(): void {
    this.stopped = true;
    this.disarmCommit();
    if (this.wdId) clearTimeout(this.wdId);
    this.wdId = 0;
  }

  /** desktop (または矩形 x,y,w,h) の RGBA を読み戻す (テスト用) */
  readback(x = 0, y = 0, w = this.canvasW, h = this.canvasH): { width: number; height: number; data: ArrayBuffer } {
    if (this.glp) return this.glp.readback(x, y, w, h);
    const img = this.g2d!.getImageData(x, y, w, h);
    return { width: w, height: h, data: img.data.buffer as ArrayBuffer };
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

  /** seqlock 検証付きで fn (surface 画素の読出し) を実行。true = 整合した読出し / false = guest が書込み中のため持ち越し */
  private stable(v: GuiView, id: number, fn: () => void): boolean {
    if (!this.seqlock) { fn(); return true; }
    const wi = (OFF.surf >> 2) + id * SURF_WORDS + S.wseq;
    for (let a = 0; a < 3; a++) {
      const w0 = Atomics.load(v.i32, wi);
      if (w0 & 1) break;
      fn();
      if (Atomics.load(v.i32, wi) === w0) { this.deferSince[id] = 0; return true; }
      this.stats.seqRetries++;
    }
    const now = performance.now();
    if (this.deferSince[id] === 0) this.deferSince[id] = now + 1;
    else if (now - this.deferSince[id] > this.staleMs) {   // 飢餓回避: staleMs 以上ずっと書込み中なら整合を諦めて読む
      fn();
      this.deferSince[id] = 0; this.stats.seqForced++;
      return true;
    }
    this.stats.seqDeferred++;
    return false;
  }

  /** surface s の client 矩形をキャンバス/surface 範囲へクリップ (空なら null) */
  private clip(s: Surf, l: number, t: number, r: number, b: number): [number, number, number, number] | null {
    l = Math.max(0, l); t = Math.max(0, t); r = Math.min(s.w, r); b = Math.min(s.h, b);
    l = Math.max(l, -s.x); t = Math.max(t, -s.y); r = Math.min(r, this.canvasW - s.x); b = Math.min(b, this.canvasH - s.y);
    return r - l <= 0 || b - t <= 0 ? null : [l, t, r, b];
  }

  /** surface s の client 矩形 [l,t,r,b) を desktop へ描く (2D) */
  private blit(s: Surf, l: number, t: number, r: number, b: number): void {
    if (!s.state || !s.visible) return;
    const c = this.clip(s, l, t, r, b);
    if (!c) return;
    [l, t, r, b] = c;
    const w = r - l, h = b - t;
    const sw = s.stride >> 2;
    const v = this.refresh();
    const src = new Uint32Array(v.buffer, s.pixels, sw * s.h);
    let img: ImageData | null = null;
    if (this.seqlock) {
      if (!this.stable(v, s.id, () => { img = this.convert(src, sw, l, t, w, h); })) { this.carry.push({ id: s.id, l, t, r, b }); return; }
    } else {
      img = this.convert(src, sw, l, t, w, h);
    }
    this.g2d!.putImageData(img!, s.x + l, s.y + t);
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
    this.g2d!.fillStyle = "#000";
    this.g2d!.fillRect(0, 0, this.canvasW, this.canvasH);
    const list: Surf[] = [];
    for (let i = 0; i < GUI_MAX_SURF; i++) { const s = this.surf(v, i); if (s.state) list.push(s); }
    list.sort((a, b) => a.z - b.z);
    for (const s of list) this.blit(s, 0, 0, s.w, s.h);
  }

  // ---------------- WebGL2 ----------------

  /** surface s の矩形 (surface 座標, クリップ済み) をテクスチャへ転送。false = seqlock で持ち越し */
  private glUpload(v: GuiView, s: Surf, l: number, t: number, r: number, b: number): boolean {
    const gl = this.glp!;
    if (!s.state || !s.pixels || !s.w || !s.h) return true;
    if (gl.ensure(s.id, s.w, s.h)) { l = 0; t = 0; r = s.w; b = s.h; }
    const mem = new Uint8Array(v.buffer, s.pixels, s.stride * s.h);
    const ok = this.stable(v, s.id, () => gl.upload(s.id, mem, s.stride, l, t, r - l, b - t));
    if (!ok) this.carry.push({ id: s.id, l, t, r, b });
    return ok;
  }

  private glDraw(s: Surf, l: number, t: number, r: number, b: number): void {
    if (!s.state || !s.visible) return;
    const c = this.clip(s, l, t, r, b);
    if (c) this.glp!.draw(s.id, c[0], c[1], c[2] - c[0], c[3] - c[1], s.x + c[0], s.y + c[1]);
  }

  /** 全 surface をテクスチャへ転送 (描画は commit で行う) */
  private glUploadAll(): void {
    const v = this.refresh();
    for (let i = 0; i < GUI_MAX_SURF; i++) {
      const s = this.surf(v, i);
      if (!s.state) this.glp!.release(i);
      else if (s.visible) this.glUpload(v, s, 0, 0, s.w, s.h);
    }
  }

  private glDrawAll(): void {
    const v = this.refresh();
    this.glp!.clear();
    const list: Surf[] = [];
    for (let i = 0; i < GUI_MAX_SURF; i++) { const s = this.surf(v, i); if (s.state) list.push(s); }
    list.sort((a, b) => a.z - b.z);
    for (const s of list) this.glDraw(s, 0, 0, s.w, s.h);
  }

  private glUploadRects(rects: DirtyRect[]): void {
    const v = this.refresh();
    for (const q of rects) {
      const s = this.surf(v, q.id);
      if (!s.state || !s.visible) continue;
      const c = this.clip(s, q.l, q.t, q.r, q.b);
      if (c) this.glUpload(v, s, c[0], c[1], c[2], c[3]);
    }
  }

  private glDrawRects(rects: DirtyRect[]): void {
    const v = this.refresh();
    const surfs: Surf[] = [];
    for (let i = 0; i < GUI_MAX_SURF; i++) surfs.push(this.surf(v, i));
    for (const q of rects) {
      const s = surfs[q.id];
      this.glDraw(s, q.l, q.t, q.r, q.b);
      const dl = s.x + q.l, dt = s.y + q.t, dr = s.x + q.r, db = s.y + q.b;
      for (const o of surfs) {
        if (o.id === q.id || !o.state || !o.visible || o.z <= s.z) continue;
        const il = Math.max(dl, o.x), it = Math.max(dt, o.y), ir = Math.min(dr, o.x + o.w), ib = Math.min(db, o.y + o.h);
        if (ir > il && ib > it) this.glDraw(o, il - o.x, it - o.y, ir - o.x, ib - o.y);
      }
    }
  }

  // ---------------- フレーム単位の遅延描画 (deferred) ----------------
  // 2 段構え: ingest = FRAME_END 時点で surface 画素を読む (seqlock 検証; GL はテクスチャへ転送, 2D は putImageData まで)。
  //           commit = 画面へ反映 (GL は quad 描画) して ack。sync "raf" では commit だけを rAF に合わせる
  //           = 「読むのは guest が静止している FRAME_END 直後」「見せるのは rAF」に分離し、rAF 待ちの間の tear を避ける。

  private raf(): ((cb: () => void) => number) | null {
    const f = (globalThis as unknown as { requestAnimationFrame?: (cb: () => void) => number }).requestAnimationFrame;
    return typeof f === "function" ? f.bind(globalThis) : null;
  }

  /** commit を予約 (raf: 次の rAF。来なければ rafTimeoutMs のタイマで commit) */
  private armCommit(): void {
    if (this.stopped || this.rafId || this.timerId) return;
    const raf = this.raf();
    if (raf) this.rafId = raf(() => { this.rafId = 0; this.stats.rafFlushes++; this.commit(); });
    this.timerId = setTimeout(() => { this.timerId = 0; this.stats.timerFlushes++; this.commit(); }, this.rafTimeoutMs);
  }

  private disarmCommit(): void {
    if (this.rafId) (globalThis as unknown as { cancelAnimationFrame?: (h: number) => void }).cancelAnimationFrame?.(this.rafId);
    if (this.timerId) clearTimeout(this.timerId);
    this.rafId = 0; this.timerId = 0;
  }

  /** ingest → commit を delayMs 後に行う (FRAME_END の来ない PRESENT の救済 / seqlock 持ち越しの再試行) */
  private armRetry(delayMs: number): void {
    if (this.stopped || this.wdId) return;
    this.wdId = setTimeout(() => {
      this.wdId = 0;
      this.ingest();
      if (this.sync === "raf") this.armCommit(); else this.commit();
    }, delayMs);
  }

  private frameEnd(seq: number): void {
    this.framesDone++;
    this.stats.frameEnds++;
    this.hasAck = true; this.ackSeq = seq;
    this.ingest();
    if (this.sync === "raf") this.armCommit();
    else { this.stats.immediateFlushes++; this.commit(); }
  }

  private ingest(): void {
    if (this.wdId) { clearTimeout(this.wdId); this.wdId = 0; }
    const t0 = performance.now();
    if (this.needRecompose) {
      this.needRecompose = false;
      this.pending.length = 0; this.carry.length = 0; this.drawRects.length = 0;
      this.stats.fullRecomposes++;
      if (this.glp) { this.glUploadAll(); this.drawAll = true; } else this.recompose();
    } else if (this.pending.length || this.carry.length) {
      const all = this.carry.concat(this.pending);
      this.stats.presents += this.pending.length;
      this.pending.length = 0; this.carry.length = 0;
      const rects = mergeRects(all);
      this.stats.rects += rects.length; this.stats.rectPixels += rectArea(rects);
      if (this.glp) { this.glUploadRects(rects); if (!this.drawAll) this.drawRects.push(...rects); }
      else for (const q of rects) this.present(q.id, q.l, q.t, q.r, q.b);
    }
    this.ingestMs += performance.now() - t0;
    if (this.carry.length) this.armRetry(4);
  }

  private commit(): void {
    this.disarmCommit();
    const t0 = performance.now();
    if (this.glp) {
      if (this.drawAll) { this.drawAll = false; this.drawRects.length = 0; this.glDrawAll(); }
      else if (this.drawRects.length) { const rs = mergeRects(this.drawRects); this.drawRects.length = 0; this.glDrawRects(rs); }
    }
    const dt = this.ingestMs + (performance.now() - t0);
    this.ingestMs = 0;
    this.stats.flushes++; this.stats.flushMs += dt; this.stats.lastFlushMs = dt; if (dt > this.stats.maxFlushMs) this.stats.maxFlushMs = dt;
    this.onFlush?.(this);
    if (this.hasAck) {
      this.hasAck = false;
      const v = this.refresh();
      Atomics.store(v.i32, W.presentDoneSeq, this.ackSeq | 0);
      Atomics.notify(v.i32, W.presentDoneSeq);
      this.post({ type: "frame", seq: this.ackSeq });
    }
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
        case CMD.SURF_CREATE: case CMD.SURF_DESTROY: case CMD.SURF_CHANGE:
          if (this.deferred) { this.needRecompose = true; this.needFlush = true; }
          else { const t0 = performance.now(); this.recompose(); this.stats.fullRecomposes++; this.legacyMs += performance.now() - t0; }
          break;
        case CMD.PRESENT:
          if (this.deferred) { this.pending.push({ id: r[1], l: r[2] | 0, t: r[3] | 0, r: r[4] | 0, b: r[5] | 0 }); this.armRetry(this.rafTimeoutMs); }
          else {
            const t0 = performance.now();
            this.present(r[1], r[2] | 0, r[3] | 0, r[4] | 0, r[5] | 0);
            this.legacyMs += performance.now() - t0;
            this.stats.presents++; this.stats.rects++; this.stats.rectPixels += Math.max(0, (r[4] | 0) - (r[2] | 0)) * Math.max(0, (r[5] | 0) - (r[3] | 0));
          }
          break;
        case CMD.FRAME_END:
          if (this.deferred) { this.needFlush = false; this.frameEnd(r[1]); }
          else {
            this.framesDone++;
            this.stats.frameEnds++; this.stats.flushes++; this.stats.flushMs += this.legacyMs; this.stats.lastFlushMs = this.legacyMs;
            if (this.legacyMs > this.stats.maxFlushMs) this.stats.maxFlushMs = this.legacyMs;
            this.legacyMs = 0;
            Atomics.store(v.i32, W.presentDoneSeq, r[1] | 0);
            Atomics.notify(v.i32, W.presentDoneSeq);
            this.post({ type: "frame", seq: r[1] });
          }
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
    if (this.needFlush) {   // SURF_* だけで FRAME_END が無かった場合 (surface の生成/変更の即時反映)
      this.needFlush = false;
      this.ingest();
      if (this.sync === "raf") this.armCommit(); else { this.stats.immediateFlushes++; this.commit(); }
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
