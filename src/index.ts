import { createAudioHarness, type AudioHarness } from "./runtime/audio";
import { setupCanvas, blitFrame, type FrameTarget } from "./runtime/canvas";

const startBtn = document.getElementById("start-audio") as HTMLButtonElement;
const statusEl = document.getElementById("status") as HTMLSpanElement;

// SAB は crossOriginIsolated が有効な場合のみ使える (vite.config.ts の COOP/COEP)
if (!crossOriginIsolated) {
  statusEl.textContent =
    "crossOriginIsolated: 無効 — COOP/COEP ヘッダを確認してください";
  console.warn("[harness] crossOriginIsolated=false: SAB 転送が使えません");
} else {
  statusEl.textContent = "crossOriginIsolated: 有効";
}

// 全画面 Canvas (FL の GUI フレーム転送先の受け皿)
const target: FrameTarget | null = setupCanvas("screen");

// 起動確認用: 黒画面に 1 枚テストフレームを blit する (putImageData 経路の疎通確認)
if (target && target.width > 0 && target.height > 0) {
  const frame = new Uint8ClampedArray(target.width * target.height * 4);
  // 中央に灰色の縞を数本 (putImageData 疎通の可視化)
  const y0 = (target.height / 4) | 0;
  const y1 = (target.height / 4 + target.height / 2) | 0;
  for (let y = y0; y < y1; y++) {
    for (let x = 0; x < target.width; x += 4) {
      const i = (y * target.width + x) * 4;
      frame[i] = frame[i + 1] = frame[i + 2] = 40; // RGB
      frame[i + 3] = 255; // A
    }
  }
  blitFrame(target, frame);
}

let harness: AudioHarness | null = null;
startBtn.disabled = !crossOriginIsolated;
startBtn.addEventListener("click", async () => {
  if (!harness) harness = createAudioHarness();
  const h = harness;
  try {
    await h.start();
    statusEl.textContent = "オーディオ: worklet 実行中 (無音スタブ)";
    // sample position は worklet マスター → メインは読み取り表示のみ
    const tick = () => {
      statusEl.textContent = `オーディオ: worklet 実行中 (無音スタブ) samplePos=${h.samplePosition()}`;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  } catch (e) {
    statusEl.textContent = `オーディオ開始に失敗: ${String(e)}`;
    console.error("[harness] audio start failed:", e);
  }
});

export {};
