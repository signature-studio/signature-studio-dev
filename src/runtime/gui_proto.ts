/**
 * gui_proto.ts — tools/gui/include/gui_proto.h の JS ミラー (オフセットは C 側 _Static_assert で固定)。
 * 共有領域 GuiShared は wasm linear memory (SharedArrayBuffer) 内の静的 1 領域。基点は wasm の gui_shared_ptr()。
 */

export const GUI_MAGIC = 0x31495547;
export const GUI_VERSION = 1;
export const GUI_MAX_SURF = 16;
export const GUI_IN_RECS = 1024;
export const GUI_OUT_RECS = 2048;
export const GUI_REC_WORDS = 8;

/** byte オフセット (GuiShared 先頭から) */
export const OFF = {
  header: 0x000,
  ptr: 0x040,
  stats: 0x080,
  inRing: 0x0c0,
  outRing: 0x100,
  surf: 0x140,
  inRecs: 0x940,
  outRecs: 0x940 + GUI_IN_RECS * 32,
  total: 0x940 + GUI_IN_RECS * 32 + GUI_OUT_RECS * 32,
} as const;

/** u32 ワード index (GuiShared 先頭から) */
export const W = {
  magic: 0, version: 1, totalSize: 2, hostReady: 3,
  screenW: 4, screenH: 5, dprX100: 6, flags: 7,
  doorbell: 8, exited: 9, exitCode: 10,
  cursorX: 16, cursorY: 17, buttons: 18, mods: 19, focused: 20, pageVisible: 21,
  keyDown: 24, // 8 words
  inPushed: 32, inDropped: 33, inConsumed: 34, outPushed: 35,
  outFullWaits: 36, presentSeq: 37, presentDoneSeq: 38, msgsDispatched: 39,
  timerFires: 40, paints: 41, framesFlushed: 42,
  inHead: 48, inTail: 49,
  outHead: 64, outTail: 65,
} as const;

/** surface 表エントリ (128B = 32 words) 内の word index */
export const S = { state: 0, visible: 1, x: 2, y: 3, w: 4, h: 5, stride: 6, pixels: 7, z: 8, gen: 9, titleByte: 64 } as const;
export const SURF_WORDS = 32;

export const IN = {
  MOUSE_MOVE: 1, MOUSE_DOWN: 2, MOUSE_UP: 3, WHEEL: 4, KEY_DOWN: 5, KEY_UP: 6, CHAR: 7, FOCUS: 8, SCREEN: 9, CLOSE: 10,
} as const;

export const CMD = {
  SURF_CREATE: 1, SURF_DESTROY: 2, SURF_CHANGE: 3, PRESENT: 4, FRAME_END: 5, SET_TITLE: 6, SET_CURSOR: 7, LOG: 8, EXIT: 9,
} as const;

export const MOD = { SHIFT: 1, CTRL: 2, ALT: 4, META: 8 } as const;

/** GuiShared への型付きビュー (Int32Array は Atomics 用) */
export class GuiView {
  readonly i32: Int32Array;
  readonly u32: Uint32Array;
  readonly u8: Uint8Array;
  constructor(readonly buffer: ArrayBufferLike, readonly base: number) {
    this.i32 = new Int32Array(buffer, base, OFF.total / 4);
    this.u32 = new Uint32Array(buffer, base, OFF.total / 4);
    this.u8 = new Uint8Array(buffer, base, OFF.total);
  }
  check(): void {
    const m = Atomics.load(this.i32, W.magic) >>> 0;
    if (m !== GUI_MAGIC) throw new Error(`[gui] bad magic 0x${m.toString(16)} at base ${this.base}`);
    const tot = this.u32[W.totalSize];
    if (tot !== OFF.total) throw new Error(`[gui] layout size mismatch: wasm=${tot} js=${OFF.total}`);
  }
}

/** DOM KeyboardEvent.code -> Windows VK */
const VK_BY_CODE: Record<string, number> = {
  Backspace: 8, Tab: 9, Enter: 13, NumpadEnter: 13, ShiftLeft: 16, ShiftRight: 16, ControlLeft: 17, ControlRight: 17,
  AltLeft: 18, AltRight: 18, Pause: 19, CapsLock: 20, Escape: 27, Space: 32, PageUp: 33, PageDown: 34, End: 35, Home: 36,
  ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40, PrintScreen: 44, Insert: 45, Delete: 46,
  MetaLeft: 0x5b, MetaRight: 0x5c, ContextMenu: 0x5d, NumLock: 0x90, ScrollLock: 0x91,
  Semicolon: 0xba, Equal: 0xbb, Comma: 0xbc, Minus: 0xbd, Period: 0xbe, Slash: 0xbf, Backquote: 0xc0,
  BracketLeft: 0xdb, Backslash: 0xdc, BracketRight: 0xdd, Quote: 0xde,
  NumpadMultiply: 0x6a, NumpadAdd: 0x6b, NumpadSubtract: 0x6d, NumpadDecimal: 0x6e, NumpadDivide: 0x6f,
};
export function vkFromCode(code: string): number {
  if (code in VK_BY_CODE) return VK_BY_CODE[code];
  let m = /^Key([A-Z])$/.exec(code);
  if (m) return m[1].charCodeAt(0);
  m = /^Digit([0-9])$/.exec(code);
  if (m) return m[1].charCodeAt(0);
  m = /^Numpad([0-9])$/.exec(code);
  if (m) return 0x60 + Number(m[1]);
  m = /^F([0-9]{1,2})$/.exec(code);
  if (m && Number(m[1]) >= 1 && Number(m[1]) <= 24) return 0x70 + Number(m[1]) - 1;
  return 0;
}

/** IDC_* (LoadCursor) -> CSS cursor */
export const CSS_CURSOR: Record<number, string> = {
  32512: "default", 32513: "text", 32514: "wait", 32515: "crosshair", 32516: "default", 32642: "nwse-resize",
  32643: "nesw-resize", 32644: "ew-resize", 32645: "ns-resize", 32646: "move", 32648: "not-allowed", 32649: "pointer",
  32650: "progress", 32651: "help",
};
