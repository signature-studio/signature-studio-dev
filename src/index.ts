import { startFlAudio, verifyToneCapture, type FlAudioSession } from "./runtime/audio_app";
import { setupCanvas, blitFrame, type FrameTarget } from "./runtime/canvas";
import { createImportForwarder } from "./runtime/imports";
import { instantiateWasm } from "./runtime/loader";
import { mountRuntimePanel } from "./runtime/boot_ui";
import { mountGuiRenderSelfTest, mountGuiSelfTest } from "./runtime/gui_boot";
import { installWebstudioContract } from "./runtime/webstudio_state";
import { installFlMcp, mountMcpPanel } from "./runtime/mcp_panel";
import { installFlMidi, mountMidiPanel } from "./runtime/midi_script";
import { installFlHelp, mountHelpPanel } from "./runtime/help_panel";

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

let session: FlAudioSession | null = null;

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
// AU-9: ユーザジェスチャ (クリック) 内で FlAudioShim.attach (OPEN→ATTACH の 2 相は wasm 側コマンドで shim が実行)。
// /?audio_capture=1 で worklet 出力をダンプし、正弦 (440/660Hz) との照合結果を window.__audio に公開する (e2e 用)。
startBtn.addEventListener("click", async () => {
  if (session) return;
  startBtn.disabled = true;
  const capture = new URLSearchParams(location.search).has("audio_capture");
  try {
    statusEl.textContent = "オーディオ: shim 起動中…";
    const s = (session = await startFlAudio({ secs: capture ? 6 : 3600, capture, log: (m) => console.log(m) }));
    const tick = () => {
      const pos = s.samplePosition();
      statusEl.textContent = pos > 0
        ? `オーディオ: worklet 実行中 (FlAudioShim テスト音 440/660Hz) samplePos=${pos} underruns=${s.underruns()}`
        : "オーディオ: shim attach 済み (OPEN/ATTACH 待ち)";
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    if (capture) {
      (window as unknown as { __audio: unknown }).__audio = {
        verify: () => (s.capture ? { ...verifyToneCapture(s.capture, s.sampleRate), sampleRate: s.sampleRate, underruns: s.underruns(), producer: s.producer(), consumer: s.consumer() } : null),
        // ネガティブコントロール用: 照合に使う sampleRate を係数倍してずらす (検出力の確認)
        verifyShifted: (k: number) => (s.capture ? verifyToneCapture(s.capture, s.sampleRate * k) : null),
      };
    }
  } catch (e) {
    session = null;
    startBtn.disabled = false;
    statusEl.textContent = `オーディオ開始に失敗: ${String(e)}`;
    console.error("[audio] start failed:", e);
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
// GUI 結線 (RT-3) — /?gui=selftest[&present=yield|blocking]。?runtime= とは独立に併用可
if (runtimeParams.get("gui") === "selftest") {
  void mountGuiSelfTest(runtimeParams);
} else if (runtimeParams.get("gui") === "render-selftest") {
  void mountGuiRenderSelfTest(runtimeParams);
}

// ---------------------------------------------------------------------------
// MCP JSON-RPC (PY-4 #77) — devtools: window.flMcp / UI: /?mcp=1
// 詳細: tools/python/BRIDGE.md。MCPTools.pyc は利用者の FL から実行時供給 (非同梱)
// ---------------------------------------------------------------------------
installFlMcp();
if (runtimeParams.has("mcp")) mountMcpPanel();

// ---------------------------------------------------------------------------
// MIDI scripting ホスト (PY-6 #76) — devtools: window.flMidi / UI: /?midi=1
// device script (.py) は利用者の FL から実行時供給 (非同梱)
// ---------------------------------------------------------------------------
installFlMidi();
if (runtimeParams.has("midi")) mountMidiPanel();

// ---------------------------------------------------------------------------
// FL Help ビューア (ST-T8 #118) — devtools: window.flHelp / UI: /?help=1
// 詳細: tools/startup/helpviewer/REPORT.md。Help の HTML は利用者の FL から実行時供給 (非同梱)・外部通信なし
// ---------------------------------------------------------------------------
installFlHelp();
if (runtimeParams.has("help")) mountHelpPanel();

export {};
