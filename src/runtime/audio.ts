/**
 * オーディオ実行系の雛形。
 *
 * 構成 (strategy.md §3 #1 / §4 M8 に対応):
 * - AudioWorklet 128 フレーム固定 (sampleRate はブラウザ実装値)。
 * - sample position は worklet 側がマスター (コントロール域に書き戻す)。
 * - メインスレッド ⇄ worklet のデータ受け渡しは SharedArrayBuffer (SPSC リング)。
 * - 音声生成は未実装 (無音 SILENCE を出力するスタブ)。将来 wasm モジュールを接続する受け皿。
 *
 * SAB レイアウト:
 *   [0 .. CONTROL_FIELDS-1] Int32 コントロール域
 *     idx 0 SAMPLE_POS : worklet → main (audio clock master, frames)
 *     idx 1 UNDERRUNS  : worklet → main (将来: リング枯渇カウンタ)
 *     idx 4 RUN_FLAG   : main → worklet (起動フラグ)
 *   [ringOffset .. ] Float32 SPSC リング (メイン→worklet, 将来の sample transport 用)
 */

export const RUN_FLAG = 7;

const CONTROL_FIELDS = 8;
const SAMPLE_POS = 0;
export const RUN_FLAG_INDEX = 4; // コントロール域 main → worklet の起動フラグ位置
const RING_FRAMES = 8192;
const RING_CHANNELS = 2;

export type AudioHarness = {
  sab: SharedArrayBuffer;
  control: Int32Array;
  /** AudioContext 開始 + worklet 登録。解決後 sample clock が動き始める。ユーザジェスチャから呼ぶこと */
  start(): Promise<void>;
  /** メイン→worklet の sample position 要求 (基本構造の受け皿。現在は記録のみ) */
  requestSamplePosition(pos: number): void;
  /** worklet がマスターの sample position を読み取り */
  samplePosition(): number;
  node: AudioWorkletNode | null;
};

export function createAudioHarness(): AudioHarness {
  const sab = new SharedArrayBuffer(
    CONTROL_FIELDS * Int32Array.BYTES_PER_ELEMENT +
      RING_FRAMES * RING_CHANNELS * Float32Array.BYTES_PER_ELEMENT,
  );
  const control = new Int32Array(sab, 0, CONTROL_FIELDS);
  const ringOffset = CONTROL_FIELDS * Int32Array.BYTES_PER_ELEMENT;
  let audioCtx: AudioContext | null = null;

  const harness: AudioHarness = {
    sab,
    control,
    node: null,
    async start() {
      // AudioContext はユーザジェスチャ内で作成する
      audioCtx ??= new AudioContext({ latencyHint: "interactive" });
      const ctx = audioCtx;
      await ctx.audioWorklet.addModule("/worklets/dummy-worklet.js");
      this.node = new AudioWorkletNode(ctx, "dummy-processor", {
        numberOfInputs: 0,
        numberOfOutputs: 1,
        outputChannelCount: [RING_CHANNELS],
        processorOptions: {
          sab,
          controlOffset: 0,
          controlFields: CONTROL_FIELDS,
          ringOffset,
          ringFrames: RING_FRAMES,
          ringChannels: RING_CHANNELS,
        },
      });
      this.node.connect(ctx.destination);
      await ctx.resume();
      Atomics.store(control, RUN_FLAG_INDEX, RUN_FLAG);
    },
    requestSamplePosition(pos: number) {
      // TODO(wasm 接続時): 位置要求を FLEngine 側の sample clock に反映する
      void pos;
    },
    samplePosition() {
      // worklet がマスター。メインは read のみ
      return Atomics.load(control, SAMPLE_POS);
    },
  };

  return harness;
}
