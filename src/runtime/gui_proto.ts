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
export const S = { state: 0, visible: 1, x: 2, y: 3, w: 4, h: 5, stride: 6, pixels: 7, z: 8, gen: 9, wseq: 10, titleByte: 64 } as const;
export const SURF_WORDS = 32;

export const IN = {
  MOUSE_MOVE: 1, MOUSE_DOWN: 2, MOUSE_UP: 3, WHEEL: 4, KEY_DOWN: 5, KEY_UP: 6, CHAR: 7, FOCUS: 8, SCREEN: 9, CLOSE: 10,
  LAYOUT: 11, IME: 12, TOUCH: 13, POINTER_LOCK: 14,
} as const;

export const CMD = {
  SURF_CREATE: 1, SURF_DESTROY: 2, SURF_CHANGE: 3, PRESENT: 4, FRAME_END: 5, SET_TITLE: 6, SET_CURSOR: 7, LOG: 8, EXIT: 9,
  POINTER_LOCK: 10, IME_POS: 11, CLIP_RECT: 12,
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
  IntlBackslash: 0xe2, NumpadMultiply: 0x6a, NumpadAdd: 0x6b, NumpadSubtract: 0x6d, NumpadDecimal: 0x6e, NumpadDivide: 0x6f,
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

/** KeyboardEvent.code -> [set 1 スキャンコード, extended]。shim の gui_core_ext.inc g_sc と同一表 (test/kbd_xcheck.sh が全件突合) */
export const SCAN_BY_CODE: Record<string, [number, number]> = {
  Escape: [0x01, 0], Digit1: [0x02, 0], Digit2: [0x03, 0], Digit3: [0x04, 0], Digit4: [0x05, 0], Digit5: [0x06, 0], Digit6: [0x07, 0],
  Digit7: [0x08, 0], Digit8: [0x09, 0], Digit9: [0x0a, 0], Digit0: [0x0b, 0], Minus: [0x0c, 0], Equal: [0x0d, 0], Backspace: [0x0e, 0], Tab: [0x0f, 0],
  KeyQ: [0x10, 0], KeyW: [0x11, 0], KeyE: [0x12, 0], KeyR: [0x13, 0], KeyT: [0x14, 0], KeyY: [0x15, 0], KeyU: [0x16, 0], KeyI: [0x17, 0], KeyO: [0x18, 0], KeyP: [0x19, 0],
  BracketLeft: [0x1a, 0], BracketRight: [0x1b, 0], Enter: [0x1c, 0], ControlLeft: [0x1d, 0],
  KeyA: [0x1e, 0], KeyS: [0x1f, 0], KeyD: [0x20, 0], KeyF: [0x21, 0], KeyG: [0x22, 0], KeyH: [0x23, 0], KeyJ: [0x24, 0], KeyK: [0x25, 0], KeyL: [0x26, 0],
  Semicolon: [0x27, 0], Quote: [0x28, 0], Backquote: [0x29, 0], ShiftLeft: [0x2a, 0], Backslash: [0x2b, 0],
  KeyZ: [0x2c, 0], KeyX: [0x2d, 0], KeyC: [0x2e, 0], KeyV: [0x2f, 0], KeyB: [0x30, 0], KeyN: [0x31, 0], KeyM: [0x32, 0],
  Comma: [0x33, 0], Period: [0x34, 0], Slash: [0x35, 0], ShiftRight: [0x36, 0], NumpadMultiply: [0x37, 0], AltLeft: [0x38, 0], Space: [0x39, 0], CapsLock: [0x3a, 0],
  F1: [0x3b, 0], F2: [0x3c, 0], F3: [0x3d, 0], F4: [0x3e, 0], F5: [0x3f, 0], F6: [0x40, 0], F7: [0x41, 0], F8: [0x42, 0], F9: [0x43, 0], F10: [0x44, 0],
  Pause: [0x45, 0], ScrollLock: [0x46, 0],
  Numpad7: [0x47, 0], Numpad8: [0x48, 0], Numpad9: [0x49, 0], NumpadSubtract: [0x4a, 0], Numpad4: [0x4b, 0], Numpad5: [0x4c, 0], Numpad6: [0x4d, 0],
  NumpadAdd: [0x4e, 0], Numpad1: [0x4f, 0], Numpad2: [0x50, 0], Numpad3: [0x51, 0], Numpad0: [0x52, 0], NumpadDecimal: [0x53, 0], F11: [0x57, 0], F12: [0x58, 0],
  NumpadEnter: [0x1c, 1], ControlRight: [0x1d, 1], NumpadDivide: [0x35, 1], PrintScreen: [0x37, 1], AltRight: [0x38, 1], NumLock: [0x45, 1],
  Home: [0x47, 1], ArrowUp: [0x48, 1], PageUp: [0x49, 1], ArrowLeft: [0x4b, 1], ArrowRight: [0x4d, 1], End: [0x4f, 1], ArrowDown: [0x50, 1], PageDown: [0x51, 1],
  Insert: [0x52, 1], Delete: [0x53, 1], MetaLeft: [0x5b, 1], MetaRight: [0x5c, 1], ContextMenu: [0x5d, 1],
  IntlBackslash: [0x56, 0],
};
/** ISO 配列の追加キー (<>|) は US 表に無いので shim 側でレイアウト表から引く (VK は 0xE2 = VK_OEM_102) */
