import { createAudioHarness, type AudioHarness } from "./runtime/audio";
import { setupCanvas, blitFrame, type FrameTarget } from "./runtime/canvas";
import { createImportForwarder } from "./runtime/imports";
import { instantiateWasm } from "./runtime/loader";
import { mountRuntimePanel } from "./runtime/boot_ui";
import { installWebstudioContract } from "./runtime/webstudio_state";

// FL 起動契約 (tools/e2e/REPORT.md §FL 起動契約)。実 FL 統合後は GuiHost の onFrame で setFrames を呼ぶ。
// このハーネスのテストフレーム (下の blitFrame) は FL の GUI フレームではないので計上しない。
export const webstudio = installWebstudioContract();

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

// ---------------------------------------------------------------------------
// ローダ スモークテスト (フェーズ 3)
//
// 最小 wasm (export add(i32,i32)->i32 のみ、imports 無し) を instantiate し、
// エクスポート関数を 1 回呼んで結果を #screen 上のステータス表示に反映する。
// 実体型は tools/misc/loader_smoke.mjs (Node) で M1 wasm でも検証済み。
// ---------------------------------------------------------------------------
const WASM_ADD_BYTES = new Uint8Array([
  0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
  // type: (i32,i32)->i32
  0x01, 0x07, 0x01, 0x60, 0x02, 0x7f, 0x7f, 0x01, 0x7f,
  // func: #0 -> type#0
  0x03, 0x02, 0x01, 0x00,
  // export "add" -> func#0
  0x07, 0x07, 0x01, 0x03, 0x61, 0x64, 0x64, 0x00, 0x00,
  // code: local なし / local.get 0 / local.get 1 / i32.add / end
  0x0a, 0x09, 0x01, 0x07, 0x00, 0x20, 0x00, 0x20, 0x01, 0x6a, 0x0b,
]);

// #screen 上に重ねるステータス表示 (index.html は触らず JS 側で追加)
const wasmStatusEl = document.createElement("div");
wasmStatusEl.style.cssText =
  "position:fixed;left:12px;bottom:12px;z-index:10;font-size:12px;color:#eee;font-family:sans-serif;";
document.body.appendChild(wasmStatusEl);

void (async () => {
  wasmStatusEl.textContent = "wasm smoke: 実行中…";
  try {
    const inst = await instantiateWasm(WASM_ADD_BYTES);
    const add = inst.exports["add"];
    if (typeof add !== "function") {
      throw new Error("export 'add' が見つかりません");
    }
    const result = (add as (a: number, b: number) => number)(40, 2);
    if (result !== 42) {
      throw new Error(`add(40,2) の戻り値が不正: ${result}`);
    }
    // fail-fast フォワーダの疎通 (呼ぶと throw すること)
    let forwarderThrew = false;
    try {
      createImportForwarder("shim_port.not_implemented_yet")(1, 2, 3);
    } catch {
      forwarderThrew = true; // 期待どおり
    }
    if (!forwarderThrew) {
      throw new Error("fail-fast フォワーダが throw しませんでした");
    }
    wasmStatusEl.textContent =
      `wasm smoke: OK — add(40,2)=${result}, fail-fast forwarder: 動作確認済`;
  } catch (e) {
    wasmStatusEl.textContent = `wasm smoke: 失敗 — ${String(e)}`;
    console.error("[harness] loader smoke failed:", e);
  }
})();

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

// ---------------------------------------------------------------------------
// ランタイム (Worker 実行基盤) — /?runtime=<id|all>&cache=…&compile=…&pump=1 で起動
// 詳細: tools/runtime/DESIGN.md
// ---------------------------------------------------------------------------
const runtimeParams = new URLSearchParams(location.search);
if (runtimeParams.has("runtime")) {
  void mountRuntimePanel(runtimeParams);
}

export {};
