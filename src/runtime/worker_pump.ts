/**
 * Win32 風メッセージポンプ (ブロッキング GetMessage を Atomics.wait で表現する方式)。
 *
 *   producer (main / GUI worker / audio など任意個, ロックフリー)
 *        └─ PumpRing.push() ──► SAB リング (Vyukov 型 bounded MPSC) ──► consumer (wasm 実行 Worker, 1 つ)
 *                                                                          └─ MessagePump.getMessage() = Atomics.wait でスリープ
 *
 * - consumer は Worker 専用 (main thread では Atomics.wait が TypeError)。AudioWorklet も不可 → worklet は producer 側のみ。
 * - ring のバイトレイアウトは pump_abi (DESIGN.md §2) として固定。同じレイアウトを wasm 共有メモリ内に置けば
 *   C 側が `memory.atomic.wait32` で直接ブロックできる (pthread ビルド用)。
 * - WM_TIMER / WM_PAINT / WM_QUIT は consumer 側で合成する (Win32 の優先順: 投稿 → QUIT → PAINT → TIMER)。
 */

export const WM = {
  NULL: 0x0000,
  PAINT: 0x000f,
  QUIT: 0x0012,
  KEYDOWN: 0x0100,
  KEYUP: 0x0101,
  CHAR: 0x0102,
  TIMER: 0x0113,
  MOUSEMOVE: 0x0200,
  LBUTTONDOWN: 0x0201,
  LBUTTONUP: 0x0202,
  MOUSEWHEEL: 0x020a,
  SIZE: 0x0005,
  /** WM_USER 以降は runtime 制御用 (ctrl 経路) にも使う */
  USER: 0x0400,
  APP_RUNTIME_STOP: 0x8001,
} as const;

/** ring ABI 定数 (i32 単位)。ヘッダ 16 i32 (=64B) + スロット 16 i32 (=64B) × capacity */
export const RING = {
  HDR_I32: 16,
  SLOT_I32: 16,
  H_ENQ: 0,
  H_DEQ: 1,
  H_WAKE: 2,
  H_CAPACITY: 4,
  H_DROPPED: 5,
  S_SEQ: 0,
  S_MSG: 1,
  S_HWND_LO: 2,
  S_HWND_HI: 3,
  S_W_LO: 4,
  S_W_HI: 5,
  S_L_LO: 6,
  S_L_HI: 7,
  S_TIME: 8,
  S_PTX: 9,
  S_PTY: 10,
  /** f64 (byte offset 48 in slot): producer の performance.timeOrigin+now (遅延計測用) */
  S_TPOST_BYTE: 48,
} as const;

export type PumpMsg = {
  hwnd: number;
  message: number;
  wLo: number;
  wHi: number;
  lLo: number;
  lHi: number;
  time: number;
  ptx: number;
  pty: number;
  tPost: number;
};

export function newPumpMsg(): PumpMsg {
  return { hwnd: 0, message: 0, wLo: 0, wHi: 0, lLo: 0, lHi: 0, time: 0, ptx: 0, pty: 0, tPost: 0 };
}

/** MAKELPARAM(x, y) の lo/hi 表現 */
export function makeLParam(x: number, y: number): { lLo: number; lHi: number } {
  return { lLo: ((y & 0xffff) << 16) | (x & 0xffff), lHi: 0 };
}

const isPow2 = (n: number) => n > 0 && (n & (n - 1)) === 0;

export class PumpRing {
  readonly i32: Int32Array;
  readonly f64: Float64Array;
  readonly capacity: number;
  private readonly mask: number;

  /** byteOffset は 64B アライン。init=true で ring を初期化 (最初の 1 者だけが行う) */
  constructor(
    readonly sab: SharedArrayBuffer,
    readonly byteOffset = 0,
    capacity?: number,
    init = false,
  ) {
    if (byteOffset % 64 !== 0) throw new Error("[pump] byteOffset は 64B アラインが必要です");
    const cap = capacity ?? Atomics.load(new Int32Array(sab, byteOffset, RING.HDR_I32), RING.H_CAPACITY);
    if (!isPow2(cap)) throw new Error(`[pump] capacity は 2 のべき乗が必要: ${cap}`);
    this.capacity = cap;
    this.mask = cap - 1;
    const words = RING.HDR_I32 + cap * RING.SLOT_I32;
    this.i32 = new Int32Array(sab, byteOffset, words);
    this.f64 = new Float64Array(sab, byteOffset, words / 2);
    if (init) {
      for (let i = 0; i < cap; i++) this.i32[RING.HDR_I32 + i * RING.SLOT_I32 + RING.S_SEQ] = i;
      Atomics.store(this.i32, RING.H_CAPACITY, cap);
    }
  }

  static byteLength(capacity: number): number {
    return (RING.HDR_I32 + capacity * RING.SLOT_I32) * 4;
  }

  static create(capacity = 1024): PumpRing {
    const sab = new SharedArrayBuffer(PumpRing.byteLength(capacity));
    return new PumpRing(sab, 0, capacity, true);
  }

  /** ロックフリー MPSC push。満杯なら false (Win32 の PostMessage 失敗相当) と dropped++ */
  push(m: Partial<PumpMsg> & { message: number }): boolean {
    const a = this.i32;
    for (;;) {
      const pos = Atomics.load(a, RING.H_ENQ);
      const base = RING.HDR_I32 + (pos & this.mask) * RING.SLOT_I32;
      const seq = Atomics.load(a, base + RING.S_SEQ);
      const dif = (seq - pos) | 0;
      if (dif === 0) {
        if (Atomics.compareExchange(a, RING.H_ENQ, pos, (pos + 1) | 0) !== pos) continue;
        a[base + RING.S_MSG] = m.message;
        a[base + RING.S_HWND_LO] = m.hwnd ?? 0;
        a[base + RING.S_HWND_HI] = 0;
        a[base + RING.S_W_LO] = m.wLo ?? 0;
        a[base + RING.S_W_HI] = m.wHi ?? 0;
        a[base + RING.S_L_LO] = m.lLo ?? 0;
        a[base + RING.S_L_HI] = m.lHi ?? 0;
        a[base + RING.S_TIME] = m.time ?? (performance.now() | 0);
        a[base + RING.S_PTX] = m.ptx ?? 0;
        a[base + RING.S_PTY] = m.pty ?? 0;
        this.f64[(base * 4 + RING.S_TPOST_BYTE) / 8] = m.tPost ?? 0;
        Atomics.store(a, base + RING.S_SEQ, (pos + 1) | 0); // publish
        Atomics.add(a, RING.H_WAKE, 1);
        Atomics.notify(a, RING.H_WAKE, 1);
        return true;
      }
      if (dif < 0) {
        Atomics.add(a, RING.H_DROPPED, 1);
        return false;
      }
      // dif > 0: 他 producer が先行。再読込
    }
  }

  /** 単一 consumer 専用 pop */
  tryPop(out: PumpMsg): boolean {
    const a = this.i32;
    const pos = Atomics.load(a, RING.H_DEQ);
    const base = RING.HDR_I32 + (pos & this.mask) * RING.SLOT_I32;
    const seq = Atomics.load(a, base + RING.S_SEQ);
    if (((seq - (pos + 1)) | 0) !== 0) return false;
    out.message = a[base + RING.S_MSG]!;
    out.hwnd = a[base + RING.S_HWND_LO]!;
    out.wLo = a[base + RING.S_W_LO]!;
    out.wHi = a[base + RING.S_W_HI]!;
    out.lLo = a[base + RING.S_L_LO]!;
    out.lHi = a[base + RING.S_L_HI]!;
    out.time = a[base + RING.S_TIME]! >>> 0;
    out.ptx = a[base + RING.S_PTX]!;
    out.pty = a[base + RING.S_PTY]!;
    out.tPost = this.f64[(base * 4 + RING.S_TPOST_BYTE) / 8]!;
    Atomics.store(a, base + RING.S_SEQ, (pos + this.capacity) | 0);
    Atomics.store(a, RING.H_DEQ, (pos + 1) | 0);
    return true;
  }

  wakeValue(): number {
    return Atomics.load(this.i32, RING.H_WAKE);
  }
  dropped(): number {
    return Atomics.load(this.i32, RING.H_DROPPED);
  }
  /** wake が expected から変化するか timeoutMs 経過までスリープ (Worker 専用) */
  wait(expected: number, timeoutMs: number): "ok" | "not-equal" | "timed-out" {
    return Atomics.wait(this.i32, RING.H_WAKE, expected, timeoutMs);
  }
}

/** この実行コンテキストで Atomics.wait が使えるか (Worker のみ true) */
export function canBlock(): boolean {
  try {
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 0);
    return true;
  } catch {
    return false;
  }
}

type Timer = { hwnd: number; id: number; interval: number; due: number };

export type PumpStats = {
  popped: number;
  waits: number;
  timedOut: number;
  timers: number;
  paints: number;
};

/** consumer 側: GetMessage / PeekMessage / SetTimer / Sleep を提供 */
export class MessagePump {
  readonly stats: PumpStats = { popped: 0, waits: 0, timedOut: 0, timers: 0, paints: 0 };
  private timers = new Map<string, Timer>();
  private paints = new Set<number>();
  private quitCode: number | null = null;
  private held: PumpMsg | null = null;
  private readonly sleepCell = new Int32Array(new SharedArrayBuffer(4));
  private readonly clock: () => number;

  constructor(readonly ring: PumpRing, clock: () => number = () => performance.now()) {
    if (!canBlock()) throw new Error("[pump] MessagePump は Worker 内でのみ作成できます (Atomics.wait 不可)");
    this.clock = clock;
  }

  postQuitMessage(code: number): void {
    this.quitCode = code;
  }
  setTimer(hwnd: number, id: number, intervalMs: number): void {
    this.timers.set(`${hwnd}:${id}`, { hwnd, id, interval: Math.max(1, intervalMs), due: this.clock() + Math.max(1, intervalMs) });
  }
  killTimer(hwnd: number, id: number): boolean {
    return this.timers.delete(`${hwnd}:${id}`);
  }
  invalidateRect(hwnd: number): void {
    this.paints.add(hwnd);
  }
  /** Sleep(): ポンプしない純粋スリープ */
  sleep(ms: number): void {
    if (ms > 0) Atomics.wait(this.sleepCell, 0, 0, ms);
  }

  private nextTimerDue(): number {
    let d = Infinity;
    for (const t of this.timers.values()) if (t.due < d) d = t.due;
    return d;
  }

  /** 非ブロッキング。メッセージを out に詰めて true / 無ければ false */
  private take(out: PumpMsg): boolean {
    if (this.held) {
      Object.assign(out, this.held);
      this.held = null;
      return true;
    }
    if (this.ring.tryPop(out)) {
      this.stats.popped++;
      return true;
    }
    if (this.quitCode !== null) {
      Object.assign(out, newPumpMsg(), { message: WM.QUIT, wLo: this.quitCode });
      return true;
    }
    for (const hwnd of this.paints) {
      this.paints.delete(hwnd);
      this.stats.paints++;
      Object.assign(out, newPumpMsg(), { message: WM.PAINT, hwnd });
      return true;
    }
    if (this.timers.size) {
      const now = this.clock();
      let best: Timer | null = null;
      for (const t of this.timers.values()) if (t.due <= now && (!best || t.due < best.due)) best = t;
      if (best) {
        best.due = Math.max(best.due + best.interval, now); // 遅延時は追いつかず 1 周期に丸める (Win32 同様 WM_TIMER は低優先で合流する)
        this.stats.timers++;
        Object.assign(out, newPumpMsg(), { message: WM.TIMER, hwnd: best.hwnd, wLo: best.id, time: now | 0 });
        return true;
      }
    }
    return false;
  }

  peekMessage(out: PumpMsg, remove: boolean): boolean {
    if (!this.take(out)) return false;
    if (!remove) this.held = { ...out };
    return true;
  }

  /** メッセージが来るか timeoutMs (Infinity 可) まで待つ。MsgWaitForMultipleObjects 相当。true=何か取得可 */
  waitForMessage(timeoutMs: number): boolean {
    const deadline = timeoutMs === Infinity ? Infinity : this.clock() + timeoutMs;
    for (;;) {
      const w = this.ring.wakeValue();
      if (this.held || this.hasPending()) return true;
      const until = Math.min(this.nextTimerDue(), deadline);
      const remain = until === Infinity ? Infinity : Math.max(0, until - this.clock());
      if (until !== Infinity && remain <= 0) {
        if (this.clock() >= deadline) return false;
        continue; // timer 満了 → hasPending で拾う
      }
      this.stats.waits++;
      if (this.ring.wait(w, remain) === "timed-out") this.stats.timedOut++;
    }
  }

  private hasPending(): boolean {
    const a = this.ring.i32;
    const pos = Atomics.load(a, RING.H_DEQ);
    const base = RING.HDR_I32 + (pos & (this.ring.capacity - 1)) * RING.SLOT_I32;
    if (((Atomics.load(a, base + RING.S_SEQ) - (pos + 1)) | 0) === 0) return true;
    if (this.quitCode !== null || this.paints.size) return true;
    const now = this.clock();
    for (const t of this.timers.values()) if (t.due <= now) return true;
    return false;
  }

  /** ブロッキング GetMessage。WM_QUIT で false。 */
  getMessage(out: PumpMsg): boolean {
    for (;;) {
      if (this.take(out)) return out.message !== WM.QUIT;
      this.waitForMessage(Infinity);
    }
  }
}
