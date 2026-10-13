/**
 * 最小 AudioWorklet スタブ (128 フレーム固定)。
 * 現状は SILENCE (無音) を出力する。設計上 sample position は worklet 側がマスター:
 * 128f ごとに samplePos を進め、コントロール域に書き戻す (メインスレッドは読み取りのみ)。
 * 将来 FLEngine wasm の DSP 出力を Float32 リングバッファ経由でここに接続する。
 *
 * SAB レイアウトは旧ハーネス (src/runtime/audio.ts, AU-9 #185 で削除済み) と対応していた。本番経路は fl-audio-worklet.js (FlAudioShim)。
 * Int32 コントロール域: [SAMPLE_POS, UNDERRUNS, -, -, RUN_FLAG, ...]
 */

const SAMPLE_POS = 0; // worklet → main (audio clock master)
const UNDERRUNS = 1; // 将来: リング枯渇カウンタ
const RUN_FLAG = 4; // main → worklet 起動フラグ
const RUN_VALUE = 7;

class DummyProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super(options);
    const o = options.processorOptions;
    this.sab = o.sab;
    this.control = new Int32Array(this.sab, o.controlOffset, o.controlFields);
    this.ring = new Float32Array(this.sab, o.ringOffset, o.ringFrames * o.ringChannels);
    this.ringFrames = o.ringFrames;
    this.ringChannels = o.ringChannels;
    this.samplePos = 0;
  }

  process(_inputs, outputs) {
    const out = outputs[0];
    const running = Atomics.load(this.control, RUN_FLAG) === RUN_VALUE;
    if (running) {
      // TODO(wasm 接続): リングバッファから FLEngine DSP 出力を取得する。
      // 取得できなかったら UNDERRUNS を増やして直前の音を維持/無音に落とす。
      // 現在はスタブ出力 (無音)。
      for (let c = 0; c < out.length; c++) {
        const ch = out[c];
        ch.fill(0); // SILENCE
      }
      void this.ring; // 将来の sample transport 用 (未使用)
      void Atomics.load(this.control, UNDERRUNS);
    } else {
      for (const ch of out) ch.fill(0);
    }
    this.samplePos += out[0].length; // 128 frames 固定
    Atomics.store(this.control, SAMPLE_POS, this.samplePos);
    return true;
  }
}

registerProcessor("dummy-processor", DummyProcessor);
