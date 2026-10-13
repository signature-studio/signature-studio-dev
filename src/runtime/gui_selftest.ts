/**
 * gui_selftest.ts — fl-runtime Worker 側の GUI 結線自己検証 (RT-3)。
 *
 * OffscreenCanvas (transferControlToOffscreen) を受け取り、PumpRing を consumer として GetMessage 相当で入力を受け、
 * 入力に応じた画面 (十字カーソル / ボタン色 / 押下キー数 / 文字列) を 2D で描く = 「入力 → ring → Worker → OffscreenCanvas → 画面」の往復を実証する。
 *
 * present 方式 (実測目的):
 *  - "yield":    メッセージを非ブロッキングで掃いたら Atomics.waitAsync でイベントループへ戻る。タスク終了ごとに frame が commit される。
 *  - "blocking": getMessage (Atomics.wait) で 1 タスク内に居座ったまま描く。実 FL の UI スレッドと同じ形。
 *                OffscreenCanvas は worker のタスク終了で commit されるため、ブロック中は画面に出ない可能性がある (検証対象)。
 */
import { MessagePump, PumpRing, RING, WM, newPumpMsg, canBlock } from "./worker_pump";
import type { GuiPresentMode, GuiSelfTestResult } from "./worker_protocol";

type Post = (m: { t: "gui-ready"; mode: GuiPresentMode } | { t: "gui-result"; result: GuiSelfTestResult }) => void;

const COLORS = { bg: "#102030", cursor: "#ffffff", left: "#ff0000", right: "#00ff00", mid: "#0000ff" };

export function guiSelfTest(msg: { ring: SharedArrayBuffer; canvas: OffscreenCanvas; width: number; height: number; present: GuiPresentMode }, post: Post): void {
  const ring = new PumpRing(msg.ring);
  const g = msg.canvas.getContext("2d", { alpha: false }) as OffscreenCanvasRenderingContext2D;
  const st = {
    lastMove: null as [number, number] | null,
    buttons: 0,
    keys: [] as number[],
    chars: "",
    focus: null as boolean | null,
    wheel: 0,
    received: 0,
    byMessage: {} as Record<string, number>,
  };

  const paint = (): void => {
    g.fillStyle = COLORS.bg;
    g.fillRect(0, 0, msg.width, msg.height);
    if (st.lastMove) {
      const [x, y] = st.lastMove;
      g.fillStyle = COLORS.cursor;
      g.fillRect(x - 6, y, 13, 1);
      g.fillRect(x, y - 6, 1, 13);
    }
    // 左上のインジケータ: 左=赤 / 右=緑 / 中=青 (押下中のみ)
    const ind: Array<[number, string]> = [[1, COLORS.left], [2, COLORS.right], [4, COLORS.mid]];
    ind.forEach(([bit, col], i) => {
      g.fillStyle = st.buttons & bit ? col : "#000000";
      g.fillRect(4 + i * 20, 4, 16, 16);
    });
    // 下端: 押下キー数 (1 キー = 4px 幅の白帯)
    g.fillStyle = "#ffffff";
    g.fillRect(4, msg.height - 12, Math.min(msg.width - 8, st.keys.length * 4), 8);
    g.fillStyle = st.focus ? "#ffff00" : "#404040";
    g.fillRect(msg.width - 20, 4, 16, 16);
  };

  const handle = (m: ReturnType<typeof newPumpMsg>): void => {
    st.received++;
    st.byMessage[m.message] = (st.byMessage[m.message] ?? 0) + 1;
    switch (m.message) {
      case WM.MOUSEMOVE: st.lastMove = [m.lLo & 0xffff, (m.lLo >>> 16) & 0xffff]; break;
      case WM.LBUTTONDOWN: st.buttons |= 1; st.lastMove = [m.lLo & 0xffff, (m.lLo >>> 16) & 0xffff]; break;
      case WM.LBUTTONUP: st.buttons &= ~1; break;
      case WM.RBUTTONDOWN: st.buttons |= 2; break;
      case WM.RBUTTONUP: st.buttons &= ~2; break;
      case WM.MBUTTONDOWN: st.buttons |= 4; break;
      case WM.MBUTTONUP: st.buttons &= ~4; break;
      case WM.MOUSEWHEEL: st.wheel += (m.wLo >> 16); break;
      case WM.KEYDOWN: case WM.SYSKEYDOWN: if (!st.keys.includes(m.wLo)) st.keys.push(m.wLo); break;
      case WM.KEYUP: case WM.SYSKEYUP: st.keys = st.keys.filter((k) => k !== m.wLo); break;
      case WM.CHAR: st.chars += String.fromCharCode(m.wLo); break;
      case WM.SETFOCUS: st.focus = true; break;
      case WM.KILLFOCUS: st.focus = false; break;
      default: break;
    }
  };

  const px = (): [number, number, number, number] | null => {
    // 検証用: 最終 MOUSEMOVE 位置の 1px 右 (十字の横棒上) を読む = 描画が確かに反映された
    const p = st.lastMove;
    if (!p) return null;
    const d = g.getImageData(p[0] + 3, p[1], 1, 1).data;
    return [d[0]!, d[1]!, d[2]!, d[3]!];
  };

  const finish = (blockedWaits: number): void => {
    paint();
    post({
      t: "gui-result",
      result: {
        mode: msg.present,
        received: st.received,
        byMessage: st.byMessage,
        lastMove: st.lastMove,
        keys: st.keys,
        chars: st.chars,
        focus: st.focus,
        wheel: st.wheel,
        blockedWaits,
        dropped: ring.dropped(),
        pixelAtLastMove: px(),
      },
    });
  };

  paint();
  const out = newPumpMsg();

  if (msg.present === "blocking") {
    if (!canBlock()) throw new Error("[gui] blocking モードは Worker が必要");
    const pump = new MessagePump(ring);
    post({ t: "gui-ready", mode: msg.present });
    while (pump.getMessage(out)) {
      if (out.message === WM.APP_RUNTIME_STOP) { pump.postQuitMessage(0); continue; }
      handle(out);
      paint();
    }
    finish(pump.stats.waits);
    return;
  }

  // yield: 非ブロッキングで掃く → waitAsync で戻る
  const tryPop = (): boolean => ring.tryPop(out);
  let waits = 0;
  const step = (): void => {
    while (tryPop()) {
      if (out.message === WM.APP_RUNTIME_STOP) { finish(waits); return; }
      handle(out);
    }
    paint();
    const w = ring.wakeValue();
    if (tryPop()) { // 取り込み直後の競合 (pop 後に push が来た場合) を取りこぼさない
      if (out.message === WM.APP_RUNTIME_STOP) { finish(waits); return; }
      handle(out);
      queueMicrotask(step);
      return;
    }
    waits++;
    const r = (Atomics as unknown as { waitAsync: (a: Int32Array, i: number, v: number) => { async: boolean; value: Promise<string> | string } }).waitAsync(ring.i32, RING.H_WAKE, w);
    if (r.async) void (r.value as Promise<string>).then(step);
    else queueMicrotask(step);
  };
  post({ t: "gui-ready", mode: msg.present });
  step();
}
