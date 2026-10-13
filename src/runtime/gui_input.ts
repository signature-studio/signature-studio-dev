/**
 * gui_input.ts — DOM 入力 → Win32 メッセージ → PumpRing.push (producer 側)。
 *
 * - 純関数 (mouseMsg / wheelMsg / keyMsg / charMsg / focusMsg) は DOM 非依存で node からも検証できる。
 * - PumpInput は <canvas> / window に DOM リスナーを付け、`worker_pump.ts` の RING ABI へ push する。
 * - マウス移動の coalesce は producer 側の責務 (DESIGN.md §2.2): 同一フレーム内の pointermove は最後の 1 件だけを push し、
 *   他種のイベント (down/up/key/wheel/focus) の直前には必ず保留中の move を吐いて順序を保つ。
 * - 座標は canvas の client 座標 (canvas 内部解像度基準)。wheel の lParam は Win32 仕様どおりスクリーン座標だが、
 *   単一 desktop モデル (tools/gui PROTOCOL §6) では client == screen。
 */
import { vkFromCode } from "./gui_proto";
import { PumpRing, WM, makeLParam, type PumpMsg } from "./worker_pump";

export const MK = { LBUTTON: 0x1, RBUTTON: 0x2, SHIFT: 0x4, CONTROL: 0x8, MBUTTON: 0x10 } as const;

export type Mods = { shift: boolean; ctrl: boolean; alt: boolean };
export type PushMsg = Partial<PumpMsg> & { message: number };

/** DOM `MouseEvent.buttons` (bit0 L, bit1 R, bit2 M) + 修飾キー → MK_* */
export function mkFlags(buttons: number, m: Mods): number {
  return (buttons & 1 ? MK.LBUTTON : 0) | (buttons & 2 ? MK.RBUTTON : 0) | (buttons & 4 ? MK.MBUTTON : 0) | (m.shift ? MK.SHIFT : 0) | (m.ctrl ? MK.CONTROL : 0);
}

export function mouseMoveMsg(hwnd: number, x: number, y: number, buttons: number, m: Mods): PushMsg {
  return { message: WM.MOUSEMOVE, hwnd, wLo: mkFlags(buttons, m), ...makeLParam(x, y), ptx: x, pty: y };
}

/** DOM `button` (0 L, 1 M, 2 R) の down/up。down 時点の buttons には当該ボタンが含まれる (up 時は含まれない) */
export function mouseButtonMsg(hwnd: number, down: boolean, button: number, x: number, y: number, buttons: number, m: Mods): PushMsg | null {
  const table: Record<number, [number, number]> = {
    0: [WM.LBUTTONDOWN, WM.LBUTTONUP],
    1: [WM.MBUTTONDOWN, WM.MBUTTONUP],
    2: [WM.RBUTTONDOWN, WM.RBUTTONUP],
  };
  const t = table[button];
  if (!t) return null; // 戻る/進むボタン等は Win32 では WM_XBUTTON*。未対応 (GUI-6)
  return { message: down ? t[0] : t[1], hwnd, wLo: mkFlags(buttons, m), ...makeLParam(x, y), ptx: x, pty: y };
}

/** WM_MOUSEWHEEL: wParam = HIWORD(delta, 120/notch, 上向き正) | LOWORD(MK_*) */
export function wheelMsg(hwnd: number, delta: number, x: number, y: number, buttons: number, m: Mods): PushMsg {
  const d = Math.max(-32768, Math.min(32767, Math.round(delta)));
  return { message: WM.MOUSEWHEEL, hwnd, wLo: ((d & 0xffff) << 16) | mkFlags(buttons, m), ...makeLParam(x, y), ptx: x, pty: y };
}

/** WM_KEYDOWN/UP (Alt 押下中は SYSKEY*)。lParam: bit0-15 repeat, bit24 ext, bit29 alt, bit30 前状態, bit31 離す遷移 */
export function keyMsg(hwnd: number, down: boolean, vk: number, repeat: boolean, alt: boolean, ext = false): PushMsg {
  const l = (1 | (ext ? 1 << 24 : 0) | (alt ? 1 << 29 : 0) | (down ? (repeat ? 1 << 30 : 0) : (1 << 30) | (1 << 31))) | 0;
  const message = alt ? (down ? WM.SYSKEYDOWN : WM.SYSKEYUP) : down ? WM.KEYDOWN : WM.KEYUP;
  return { message, hwnd, wLo: vk, lLo: l };
}

export function charMsg(hwnd: number, ch: number, repeat: boolean): PushMsg {
  return { message: WM.CHAR, hwnd, wLo: ch, lLo: 1 | (repeat ? 1 << 30 : 0) };
}

export function focusMsg(hwnd: number, focused: boolean): PushMsg {
  return { message: focused ? WM.SETFOCUS : WM.KILLFOCUS, hwnd };
}

/** KeyboardEvent → 文字コード (WM_CHAR 合成。0 = 文字を生まない) */
export function charOf(e: { key: string; ctrlKey: boolean; metaKey: boolean }): number {
  if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) return e.key.charCodeAt(0);
  if (e.key === "Enter") return 13;
  if (e.key === "Backspace") return 8;
  if (e.key === "Tab") return 9;
  if (e.key === "Escape") return 27;
  return 0;
}

export type PumpInputStats = {
  /** 受けた pointermove 数 */
  movesSeen: number;
  /** coalesce で捨てた pointermove 数 */
  movesCoalesced: number;
  /** ring へ push 成功した全メッセージ数 */
  pushed: number;
  /** ring 満杯で push 失敗した数 (PostMessage 失敗相当) */
  rejected: number;
};

export type PumpInputOptions = {
  canvas: HTMLCanvasElement;
  ring: PumpRing;
  /** 投稿先 hwnd (既定 0) */
  hwnd?: number;
  /** 保留 move の吐き出しタイミング。既定は requestAnimationFrame */
  schedule?: (fn: () => void) => void;
};

export class PumpInput {
  readonly stats: PumpInputStats = { movesSeen: 0, movesCoalesced: 0, pushed: 0, rejected: 0 };
  private readonly canvas: HTMLCanvasElement;
  private readonly ring: PumpRing;
  private readonly hwnd: number;
  private readonly schedule: (fn: () => void) => void;
  private pending: PushMsg | null = null;
  private scheduled = false;
  private readonly off: Array<() => void> = [];

  constructor(o: PumpInputOptions) {
    this.canvas = o.canvas;
    this.ring = o.ring;
    this.hwnd = o.hwnd ?? 0;
    this.schedule = o.schedule ?? ((fn) => requestAnimationFrame(() => fn()));
    this.bind();
  }

  dispose(): void {
    for (const f of this.off) f();
    this.off.length = 0;
  }

  /** 保留中の move を ring へ吐く */
  flush(): void {
    const m = this.pending;
    if (!m) return;
    this.pending = null;
    this.send(m);
  }

  private send(m: PushMsg): void {
    if (this.ring.push({ ...m, tPost: performance.timeOrigin + performance.now() })) this.stats.pushed++;
    else this.stats.rejected++;
  }

  /** move 以外: 先に保留 move を吐いてから push (順序保存) */
  private post(m: PushMsg | null): void {
    if (!m) return;
    this.flush();
    this.send(m);
  }

  private pos(e: MouseEvent): [number, number] {
    const r = this.canvas.getBoundingClientRect();
    return [Math.round((e.clientX - r.left) * (this.canvas.width / r.width)), Math.round((e.clientY - r.top) * (this.canvas.height / r.height))];
  }
  private mods(e: MouseEvent | KeyboardEvent): Mods {
    return { shift: e.shiftKey, ctrl: e.ctrlKey, alt: e.altKey };
  }

  private on<K extends keyof HTMLElementEventMap>(t: EventTarget, type: string, fn: (e: HTMLElementEventMap[K]) => void, opts?: AddEventListenerOptions): void {
    t.addEventListener(type, fn as EventListener, opts);
    this.off.push(() => t.removeEventListener(type, fn as EventListener, opts));
  }

  private bind(): void {
    const c = this.canvas;
    c.tabIndex = 0;
    this.on<"pointermove">(c, "pointermove", (e) => {
      const [x, y] = this.pos(e);
      this.stats.movesSeen++;
      if (this.pending) this.stats.movesCoalesced++;
      this.pending = mouseMoveMsg(this.hwnd, x, y, e.buttons, this.mods(e));
      if (!this.scheduled) {
        this.scheduled = true;
        this.schedule(() => { this.scheduled = false; this.flush(); });
      }
    });
    this.on<"pointerdown">(c, "pointerdown", (e) => {
      c.setPointerCapture?.(e.pointerId);
      c.focus?.();
      const [x, y] = this.pos(e);
      this.post(mouseButtonMsg(this.hwnd, true, e.button, x, y, e.buttons, this.mods(e)));
    });
    this.on<"pointerup">(c, "pointerup", (e) => {
      const [x, y] = this.pos(e);
      this.post(mouseButtonMsg(this.hwnd, false, e.button, x, y, e.buttons, this.mods(e)));
    });
    this.on<"wheel">(c, "wheel", (e) => {
      e.preventDefault();
      const [x, y] = this.pos(e);
      const unit = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? 400 : 100;
      this.post(wheelMsg(this.hwnd, (-e.deltaY / unit) * 120, x, y, e.buttons, this.mods(e)));
    }, { passive: false });
    this.on<"contextmenu">(c, "contextmenu", (e) => e.preventDefault());
    const key = (down: boolean) => (e: KeyboardEvent) => {
      const vk = vkFromCode(e.code);
      if (!vk) return;
      e.preventDefault();
      this.post(keyMsg(this.hwnd, down, vk, e.repeat, e.altKey));
      if (down) {
        const ch = charOf(e);
        if (ch) this.post(charMsg(this.hwnd, ch, e.repeat));
      }
    };
    this.on<"keydown">(window, "keydown", key(true) as (e: KeyboardEvent) => void);
    this.on<"keyup">(window, "keyup", key(false) as (e: KeyboardEvent) => void);
    this.on<"focus">(window, "focus", () => this.post(focusMsg(this.hwnd, true)));
    this.on<"blur">(window, "blur", () => this.post(focusMsg(this.hwnd, false)));
  }
}
