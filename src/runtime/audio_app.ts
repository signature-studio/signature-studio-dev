/**
 * アプリ本体 (src/index.ts) 向けの FlAudioShim 組込み層 (AU-9)。
 *
 * - ユーザジェスチャ (クリック) 内から呼ぶ。wasm ロード → FlAudioShim.attach (レイアウト 59 項目照合) まで行い、
 *   AudioContext 生成・worklet ロード・ATTACH は wasm 側の OPEN/ATTACH コマンドで shim が行う (OPEN→ATTACH の 2 相)。
 * - リング仕様は tools/audio/docs/PROTOCOL.md、レイアウトは tools/audio/src/flaudio.h (単一の真実)。
 * - 現状の producer は tools/audio のテスト wasm (fla_test: 440/660Hz 正弦)。FL 本体 wasm の接続時は
 *   loadToneWasm を差し替えるだけでよい (FlAudioWasmApi の 5 関数が接点)。
 */
import { FlAudioShim, type FlAudioWasmApi, type FlCaptureSpec, type ProducerStats } from "./audio-shim";

/** vite の base が / 以外でも解決できるよう document.baseURI 基準にする (public/worklets/ を配置) */
export const WORKLET_URL = new URL("worklets/fl-audio-worklet.js", document.baseURI).href;
/** tools/audio/integration/stage_app.sh がハッシュ名で stage したテスト音 wasm の manifest ({glue, wasm})。glue は pthread Worker スクリプトも兼ねる */
export const TONE_MANIFEST_URL = "/wasm/audio/manifest.json";

async function resolveToneGlue(): Promise<string> {
  const res = await fetch(TONE_MANIFEST_URL);
  if (!res.ok) throw new Error(`テスト音 manifest 取得失敗: ${TONE_MANIFEST_URL} HTTP ${res.status} (stage_app.sh を実行したか?)`);
  const m = (await res.json()) as { glue: string };
  return new URL(`/wasm/audio/${m.glue}`, location.href).href;
}

interface ToneModule {
  wasmMemory: WebAssembly.Memory;
  _fla_ctl_ptr(): number;
  _fla_layout_count(): number;
  _fla_layout_off(i: number): number;
  _fla_layout_name(i: number): number;
  _fla_test_done_ptr(): number;
  UTF8ToString(p: number): string;
}

export function loadToneWasm(glueUrl: string, args: string[], log: (s: string) => void): Promise<ToneModule> {
  return new Promise((resolve, reject) => {
    const g = window as unknown as { Module?: Record<string, unknown> };
    g.Module = {
      arguments: args,
      print: (t: string) => log(`[wasm] ${t}`),
      printErr: (t: string) => log(`[wasm!] ${t}`),
      onAbort: (w: unknown) => reject(new Error(`wasm abort: ${String(w)}`)),
      onRuntimeInitialized: () => resolve(g.Module as unknown as ToneModule),
    };
    const s = document.createElement("script");
    s.src = glueUrl;
    s.onerror = () => reject(new Error(`glue 取得失敗: ${glueUrl}`));
    document.body.appendChild(s);
  });
}

export interface StartOptions {
  /** テスト音の長さ (秒)。producer はこの長さで停止する */
  secs?: number;
  /** true なら worklet 出力を SAB にダンプし verifyToneCapture で正弦照合できるようにする (自己検査用) */
  capture?: boolean;
  glueUrl?: string;
  log?: (s: string) => void;
}

export interface FlAudioSession {
  shim: FlAudioShim;
  capture: FlCaptureSpec | null;
  sampleRate: number;
  /** worklet がマスターのサンプル位置 (128f 単位で進む) */
  samplePosition(): number;
  underruns(): number;
  /** producer の起床統計 (失敗時に producer 遅延の有無を見る) */
  producer(): ProducerStats;
  dispose(): void;
}

const TONE_SR = 48000;

/** クリック等のユーザジェスチャから呼ぶ。attach 完了で resolve (音声の開始は wasm の OPEN/ATTACH 後に非同期で起きる) */
export async function startFlAudio(o: StartOptions = {}): Promise<FlAudioSession> {
  const log = o.log ?? ((s: string) => console.log(s));
  const secs = o.secs ?? 30;
  const mod = await loadToneWasm(
    o.glueUrl ?? (await resolveToneGlue()),
    ["api=asio", "mode=sine", "buf=256", "depth=2", `secs=${secs}`, `sr=${TONE_SR}`],
    log,
  );
  const api: FlAudioWasmApi = {
    getBuffer: () => mod.wasmMemory.buffer as unknown as SharedArrayBuffer,
    ctlPtr: () => mod._fla_ctl_ptr(),
    layoutCount: () => mod._fla_layout_count(),
    layoutOff: (i) => mod._fla_layout_off(i),
    layoutName: (i) => mod.UTF8ToString(mod._fla_layout_name(i)),
  };
  let sampleRate = TONE_SR;
  const shim = new FlAudioShim(api, {
    workletUrl: WORKLET_URL,
    log,
    captureFactory: o.capture
      ? (outCh, inCh) => {
          const frames = Math.ceil((secs * TONE_SR + 8192) / 128) * 128;
          const bytes = 64 + frames * (outCh + inCh) * 4 + (frames / 128) * 4;
          return { sab: new SharedArrayBuffer(bytes), frames, outCh, inCh };
        }
      : undefined,
    onNode: (ctx) => { sampleRate = ctx.sampleRate; },
  });
  shim.attach();
  return {
    shim,
    get capture() { return shim.lastCapture; },
    get sampleRate() { return sampleRate; },
    samplePosition: () => (shim.snapshot().quanta ?? 0) * 128,
    underruns: () => shim.snapshot().underruns ?? 0,
    producer: () => shim.producerStats(),
    dispose: () => shim.dispose(),
  };
}

export interface ToneCheck {
  covered_frames: number;
  max_abs_err: number;
  peak: number;
  rms: number;
  zero_runs_ge16: number;
  /** 最初に理論値から 1e-5 を超えた出力フレーム (無ければ -1) */
  first_err_frame: number;
  /** 最初に 16 フレーム連続無音になった開始フレーム (無ければ -1) */
  first_zero_run_frame: number;
  /** worklet が capture ヘッダへ記録した underrun 件数・最初/最後の underrun の出力 quantum 位置 (frame = quantum*128) */
  underrun_count: number;
  first_underrun_frame: number;
  last_underrun_frame: number;
  /** 最初の underrun 直前の出力リング充填量 (frames, worklet が consume 前に記録。-1 = 無し) */
  fill_at_first_underrun: number;
  /** 最初の underrun までの 32 quantum 内の充填量最小値 (producer 遅延なら低下が先行する。-1 = 無し) */
  fill_min_before_first_underrun: number;
  /** 最初の underrun までの 32 quantum の充填量の推移 (古い順・最後が underrun の quantum。underrun 無しは空) */
  fill_trace_before_first_underrun: number[];
  /** audio callback 間隔の最大 (ms) と 20ms 超の回数 (consumer 側の停止の観測) */
  cb_gap_max_ms: number;
  cb_gap_over20_count: number;
}

/** capture ダンプを 440Hz(L)/660Hz(R) 振幅 0.5 の理論値と照合する (tools/audio/test/page.mjs verify と同じ式) */
export function verifyToneCapture(cap: FlCaptureSpec, sr: number): ToneCheck {
  const hdr = new Int32Array(cap.sab, 0, 16);
  const covered = Atomics.load(hdr, 0);
  const out = new Float32Array(cap.sab, 64, cap.frames * cap.outCh);
  const ch0 = out.subarray(0, cap.frames), ch1 = out.subarray(cap.frames, 2 * cap.frames);
  let maxErr = 0, peak = 0, ss = 0, runs = 0, run = 0, firstErr = -1, firstRun = -1;
  for (let p = 0; p < covered; p++) {
    const e0 = 0.5 * Math.sin((2 * Math.PI * 440 * p) / sr);
    const e1 = 0.5 * Math.sin((2 * Math.PI * 660 * p) / sr);
    const err = Math.max(Math.abs(ch0[p] - e0), Math.abs(ch1[p] - e1));
    if (err > 1e-5 && firstErr < 0) firstErr = p;
    maxErr = Math.max(maxErr, err);
    peak = Math.max(peak, Math.abs(ch0[p]));
    ss += ch0[p] * ch0[p];
    if (ch0[p] === 0) { run++; if (run === 16) { runs++; if (firstRun < 0) firstRun = p - 15; } } else run = 0;
  }
  const uc = Atomics.load(hdr, 6);
  // worklet は quantum ごとの充填量 fill[q] (consume 前の out_write-out_read) を記録する。最初の underrun 周辺の充填推移を読む
  const fillLen = Math.floor(cap.frames / 128);
  const fill = new Int32Array(cap.sab, 64 + cap.frames * (cap.outCh + cap.inCh) * 4, fillLen);
  const q0 = uc ? Atomics.load(hdr, 4) : -1;
  const fillAt = q0 >= 0 && q0 < fillLen ? fill[q0] : -1;
  let fillMin = -1;
  const trace: number[] = [];
  if (q0 >= 0 && q0 < fillLen) {
    fillMin = fill[q0];
    for (let q = Math.max(0, q0 - 31); q <= q0; q++) { fillMin = Math.min(fillMin, fill[q]); trace.push(fill[q]); }
  }
  return {
    covered_frames: covered, max_abs_err: maxErr, peak, rms: covered ? Math.sqrt(ss / covered) : 0, zero_runs_ge16: runs,
    first_err_frame: firstErr, first_zero_run_frame: firstRun,
    underrun_count: uc, first_underrun_frame: uc ? q0 * 128 : -1, last_underrun_frame: uc ? Atomics.load(hdr, 5) * 128 : -1,
    fill_at_first_underrun: fillAt, fill_min_before_first_underrun: fillMin, fill_trace_before_first_underrun: trace,
    cb_gap_max_ms: Atomics.load(hdr, 14), cb_gap_over20_count: Atomics.load(hdr, 12) + Atomics.load(hdr, 13),
  };
}
