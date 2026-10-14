/**
 * FL audio shim — メインスレッド側コントローラ。
 *
 * wasm スレッド (FL エンジン / shim) は AudioContext / getUserMedia / WebMIDI に触れられない
 * (worker に AudioContext は無い) ため、制御面はここ (main thread) が担当する:
 *   - wasm 共有メモリ上のコマンドメールボックス (cmd_seq/ack_seq) を Atomics.waitAsync で待ち受け
 *   - OPEN: AudioContext + AudioWorkletNode (fl-audio-shim) を生成して ack
 *   - 時刻対応 (getOutputTimestamp → ref_*) とレイテンシ値を ctl に定期公開
 *   - AudioContext の状態変化を dev_events で wasm へ通知 (ASIO kAsioResetRequest の元)
 * 設計: tools/audio/docs/PROTOCOL.md
 */
import { FLA_CMD, FLA_EV, FLA_LAYOUT, verifyLayout, type FlaField } from "./audio-layout";
import type { FlAudioInput } from "./audio-input";

/** wasm モジュールへの薄い口 (Emscripten Module / 自前 instance いずれからも作れる) */
export interface FlAudioWasmApi {
  /** 現在の wasm 共有メモリ。memory.grow 後は新しい SAB が返る */
  getBuffer(): SharedArrayBuffer;
  ctlPtr(): number;
  layoutCount(): number;
  layoutOff(i: number): number;
  layoutName(i: number): string;
}

export interface FlCaptureSpec {
  sab: SharedArrayBuffer;
  frames: number;
  outCh: number;
  inCh: number;
  /** true なら frames 容量の ring として扱う (絶対フレーム p は p % frames へ書く。照合側が未照合区間を畳み込む) */
  ring?: boolean;
}

/** producer (ASIO bufferSwitch 側の fla_out_wait_fill_le) の起床統計。wake_hist は worklet の notify から producer 起床までの遅延 (ms: <1,<2,<4,<8,<16,>=16) */
export interface ProducerStats {
  wake_hist: number[];
  wake_count: number;
  wait_timeouts: number;
}

export interface FlAudioShimOptions {
  workletUrl: string;
  /** OPEN 毎にテスト用ダンプ領域を割り当てる (本番は未指定 = ダンプ無し) */
  captureFactory?: (outCh: number, inCh: number) => FlCaptureSpec | null;
  /** ノード生成直後に呼ばれる (入力ソース接続等のフック) */
  onNode?: (ctx: AudioContext, node: AudioWorkletNode) => void | Promise<void>;
  /** 入力デバイス管理。in_ch>0 の ATTACH 毎に worklet node へ接続し、入力喪失は kAsioResetRequest として wasm へ通知する */
  input?: FlAudioInput;
  /**
   * ASIO::controlPanel (FL の asiopanelbtn) の UI 代替。入力デバイス選択パネルなどを開く。未指定なら controlPanel は NotPresent。
   * 契約: UI を開いて即返すこと。shim のコマンドループは await 中ブロックされ、C 側の待ちを超えると ASE_NotPresent になる。
   */
  controlPanel?: () => void | Promise<void>;
  log?: (msg: string) => void;
  /** getOutputTimestamp の採取ログ (テスト用: 時刻対応の傾き検証) */
  refLog?: { ctxTime: number; epochMs: number }[];
  /** AudioContext 作成オプションの上書き (テスト用) */
  contextOptions?: AudioContextOptions;
  /** outputLatency (秒) の読み出しの差し替え (テスト用: 起動直後 0 → 後から更新される環境の再現)。既定は ctx.outputLatency */
  readOutputLatency?: (ctx: AudioContext) => number;
  /** ATTACH 時に outputLatency が 0 の間待つ上限 (ms, 既定 600, 0 で待たない)。FL は createBuffers 直後の getLatencies で一度だけ読むため
   *  (FLEngine 0xc58348, AU-7 #193)、起動直後の 0 を読ませないための吸収。上限まで 0 のままのブラウザ (未実装/常時 0) は 0 のまま進む */
  outputLatencyWaitMs?: number;
}

type WaitAsyncResult = { async: false; value: "not-equal" | "timed-out" } | { async: true; value: Promise<"ok" | "timed-out"> };
const waitAsync = (ia: Int32Array, idx: number, val: number): WaitAsyncResult =>
  (Atomics as unknown as { waitAsync(ia: Int32Array, i: number, v: number): WaitAsyncResult }).waitAsync(ia, idx, val);

/** flaudio.h FLA_E_NO_PANEL */
const FLA_E_NO_PANEL = -3;

const HINTS: (AudioContextLatencyCategory | number)[] = ["interactive", "balanced", "playback", 0];

export class FlAudioShim {
  private i32!: Int32Array;
  private i64f = new Float64Array(1);
  private i64u = new Uint32Array(this.i64f.buffer);
  private ctx: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private disposed = false;
  private refTimer: ReturnType<typeof setInterval> | null = null;
  private moduleLoadedFor: AudioContext | null = null;
  private pendingOpen: { outCh: number; inCh: number } | null = null;
  private ctlPtr = 0;
  private offInput: (() => void) | null = null;
  controlPanelCalls = 0;
  lastCapture: FlCaptureSpec | null = null;
  workletErrors: string[] = [];
  clockJumpLog: { q: number; d: number; frame: number; prev: number; ms: number }[] = [];
  commandsHandled = 0;
  private refPts: { x: number; y: number }[] = [];

  constructor(private api: FlAudioWasmApi, private opts: FlAudioShimOptions) {}

  get context(): AudioContext | null { return this.ctx; }
  get node_(): AudioWorkletNode | null { return this.node; }
  private log(m: string) { this.opts.log?.(`[audio-shim] ${m}`); }
  private outLat(ctx: AudioContext): number { return (this.opts.readOutputLatency ? this.opts.readOutputLatency(ctx) : ctx.outputLatency) || 0; }

  private ix(f: FlaField): number { return FLA_LAYOUT[f] >> 2; }
  private ld(f: FlaField): number { return Atomics.load(this.i32, this.ix(f)); }
  private st(f: FlaField, v: number) { Atomics.store(this.i32, this.ix(f), v | 0); }

  /** wasm ロード後に呼ぶ。レイアウト自己検証 → コマンドループ開始 */
  attach(): void {
    const n = this.api.layoutCount();
    verifyLayout(n, (i) => this.api.layoutOff(i), (i) => this.api.layoutName(i));
    this.ctlPtr = this.api.ctlPtr();
    this.i32 = new Int32Array(this.api.getBuffer(), this.ctlPtr, 96);
    this.st("ctrl_ready", 1);
    Atomics.notify(this.i32, this.ix("ctrl_ready"));
    this.offInput = this.opts.input?.on((e) => {
      if (e.type === "lost") this.postDevEvent(FLA_EV.INPUT_CHANGED);
    }) ?? null;
    this.log(`attached ctl@${this.ctlPtr} (layout ${n} fields OK)`);
    void this.loop();
  }

  dispose(): void {
    this.disposed = true;
    this.offInput?.();
    this.opts.input?.disconnect();
    if (this.refTimer) clearInterval(this.refTimer);
    this.node?.disconnect();
    void this.ctx?.close();
    Atomics.notify(this.i32, this.ix("cmd_seq"));
  }

  private async loop(): Promise<void> {
    const iSeq = this.ix("cmd_seq");
    while (!this.disposed) {
      const seq = Atomics.load(this.i32, iSeq);
      if (seq !== this.ld("ack_seq")) {
        let status = 0;
        const res = [0, 0, 0, 0];
        try { status = await this.handle(res); } catch (e) {
          this.log(`command ${this.ld("cmd_op")} failed: ${(e as Error).stack ?? e}`);
          status = -1;
        }
        this.commandsHandled++;
        for (let k = 0; k < 4; k++) Atomics.store(this.i32, this.ix("ack_res") + k, res[k] | 0);
        this.st("ack_status", status);
        Atomics.store(this.i32, this.ix("ack_seq"), seq);
        Atomics.notify(this.i32, this.ix("ack_seq"));
        continue;
      }
      const r = waitAsync(this.i32, iSeq, seq);
      if (r.async) await r.value;
    }
  }

  private async handle(res: number[]): Promise<number> {
    const op = this.ld("cmd_op");
    const a = [0, 1, 2, 3].map((k) => Atomics.load(this.i32, this.ix("cmd_arg") + k) >>> 0);
    switch (op) {
      case FLA_CMD.OPEN: return this.cmdOpen(a[0], a[3], res);
      case FLA_CMD.ATTACH: return this.cmdAttach(a[0], res);
      case FLA_CMD.CLOSE: return this.cmdClose();
      case FLA_CMD.RESUME: await this.ctx?.resume(); return 0;
      case FLA_CMD.SET_SR: return this.cmdSetSr(a[0]);
      case FLA_CMD.CONTROL_PANEL: return this.cmdControlPanel();
      default:
        this.log(`unimplemented command op=${op} (fail-fast)`);
        return -2;
    }
  }

  private async ensureContext(sr: number, hint: number): Promise<AudioContext> {
    if (this.ctx && this.ctx.sampleRate === sr && this.ctx.state !== "closed") return this.ctx;
    if (this.ctx) { this.teardownNode(); await this.ctx.close().catch(() => {}); }
    const ctx = new AudioContext({
      latencyHint: HINTS[hint] ?? "interactive",
      sampleRate: sr,
      ...this.opts.contextOptions,
    });
    ctx.onstatechange = () => this.onState(ctx);
    this.ctx = ctx;
    this.moduleLoadedFor = null;
    return ctx;
  }

  private onState(ctx: AudioContext): void {
    if (ctx !== this.ctx) return;
    const s = ctx.state as string;
    this.log(`AudioContext state -> ${s}`);
    let ev = 0;
    if (s === "suspended" || s === "interrupted") ev = FLA_EV.SUSPENDED;
    else if (s === "closed") ev = FLA_EV.CLOSED;
    else if (s === "running") ev = FLA_EV.RESUMED;
    if (ev) this.postDevEvent(ev);
  }

  /** dev_events にビットを立て、out_read 待ちの producer を起こす (producer は起床時に exchange で消費して kAsioResetRequest を発行) */
  private postDevEvent(ev: number): void {
    if (!this.i32) return;
    Atomics.or(this.i32, this.ix("dev_events"), ev);
    Atomics.notify(this.i32, this.ix("out_read"));
  }

  private teardownNode(): void {
    this.opts.input?.disconnect();
    if (this.refTimer) { clearInterval(this.refTimer); this.refTimer = null; }
    if (this.node) { this.node.disconnect(); this.node.port.close(); this.node = null; }
  }

  /** ブラウザ音声スレッドの実バースト長 (frames) を 96 quanta の観測で較正する。resume 後 ~0.25 s。失敗時は 0 */
  private async probeBurst(ctx: AudioContext): Promise<number> {
    try {
      await ctx.resume();
      const probe = new AudioWorkletNode(ctx, "fl-burst-probe", { numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [1] });
      probe.connect(ctx.destination);
      const max = await new Promise<number>((ok) => {
        const t = setTimeout(() => ok(0), 3000);
        probe.port.onmessage = (e: MessageEvent) => { clearTimeout(t); ok((e.data as { max: number }).max); };
      });
      probe.disconnect();
      return max;
    } catch (e) {
      this.log(`burst probe failed: ${e}`);
      return 0;
    }
  }

  /** phase 1: AudioContext 生成 + worklet module ロード。ブラウザの音声コールバック粒度 (burst) を返す */
  private async cmdOpen(sr: number, hint: number, res: number[]): Promise<number> {
    const ctx = await this.ensureContext(sr, hint);
    this.teardownNode();
    this.refPts = [];
    if (this.moduleLoadedFor !== ctx) {
      await ctx.audioWorklet.addModule(this.opts.workletUrl);
      this.moduleLoadedFor = ctx;
    }
    const probed = await this.probeBurst(ctx);
    res[0] = Math.max(Math.round((ctx.baseLatency || 0) * ctx.sampleRate), probed);
    res[1] = ctx.sampleRate;
    res[2] = Math.round(this.outLat(ctx) * 1e6);
    this.pendingOpen = { outCh: 0, inCh: 0 };
    this.log(`OPEN sr=${ctx.sampleRate} baseLatency=${ctx.baseLatency} probed_burst=${probed} -> burst ${res[0]} frames state=${ctx.state}`);
    return 0;
  }

  /** phase 2: ring 確保後。最新の wasm SAB と ctl/layout を processorOptions で渡して node を生成 */
  private async cmdAttach(_unused: number, res: number[]): Promise<number> {
    void res;
    const ctx = this.ctx;
    if (!ctx || !this.pendingOpen) throw new Error("ATTACH without OPEN");
    const outCh = this.ld("out_ch"), inCh = this.ld("in_ch");
    this.pendingOpen = null;
    this.teardownNode();
    const layout: Record<string, number> = { ...FLA_LAYOUT };
    this.lastCapture = this.opts.captureFactory?.(outCh, inCh) ?? null;
    const node = new AudioWorkletNode(ctx, "fl-audio-shim", {
      numberOfInputs: inCh > 0 ? 1 : 0,
      numberOfOutputs: 1,
      outputChannelCount: [outCh],
      channelCount: Math.max(inCh, 1),
      channelCountMode: "explicit",
      channelInterpretation: "speakers",
      processorOptions: {
        buffer: this.api.getBuffer(),   // fla_open の malloc 後 (= ring 確保後) の最新 SAB
        ctlPtr: this.ctlPtr,
        layout,
        capture: this.lastCapture,
      },
    });
    node.port.onmessage = (e: MessageEvent) => {
      const d = e.data as { type: string; message?: string; q?: number; d?: number; frame?: number; prev?: number; ms?: number };
      if (d.type === "error") { this.workletErrors.push(d.message ?? "?"); this.log(`worklet error: ${d.message}`); }
      if (d.type === "clock_jump") this.clockJumpLog.push({ q: d.q ?? -1, d: d.d ?? 0, frame: d.frame ?? -1, prev: d.prev ?? -1, ms: d.ms ?? 0 });
    };
    node.connect(ctx.destination);
    this.node = node;
    await this.opts.onNode?.(ctx, node);
    if (this.opts.input && inCh > 0) {
      // 入力の失敗 (権限拒否・デバイス無し) で出力を巻き込まない: 入力は無音のまま継続し、UI へは input.on("error") で伝わる
      await this.opts.input.connect(ctx, node).catch((e) => this.log(`input connect failed: ${(e as Error).message ?? e}`));
    }
    await ctx.resume();
    const waited = await this.waitOutputLatency(ctx);
    this.updateRef();
    this.refTimer = setInterval(() => this.updateRef(), 250);
    this.log(`ATTACH out=${outCh} in=${inCh} ring=${this.ld("ring_frames")} depth=${this.ld("depth")} outLat=${this.outLat(ctx)} waited=${waited.toFixed(0)}ms state=${ctx.state}`);
    return 0;
  }

  private async cmdControlPanel(): Promise<number> {
    if (!this.opts.controlPanel) return FLA_E_NO_PANEL;
    this.controlPanelCalls++;
    await this.opts.controlPanel();
    return 0;
  }

  /** outputLatency が 0 の間 (起動直後は約 250ms 0 のまま) 最大 outputLatencyWaitMs だけ待つ。待った ms を返す */
  private async waitOutputLatency(ctx: AudioContext): Promise<number> {
    const max = this.opts.outputLatencyWaitMs ?? 600;
    const t0 = performance.now();
    while (!(this.outLat(ctx) > 0) && performance.now() - t0 < max) await new Promise<void>((r) => setTimeout(r, 20));
    return performance.now() - t0;
  }

  private async cmdClose(): Promise<number> {
    this.pendingOpen = null;
    this.teardownNode();
    if (this.ctx) { const c = this.ctx; this.ctx = null; this.moduleLoadedFor = null; await c.close().catch(() => {}); }
    return 0;
  }

  /** SET_SR: ASIO setSampleRate。AudioContext を作り直し、同じ ring に node を再接続する (producer 停止中のみ) */
  private async cmdSetSr(sr: number): Promise<number> {
    const res = [0, 0, 0, 0];
    await this.cmdOpen(sr, 0, res);
    return this.cmdAttach(0, res);
  }

  /** getOutputTimestamp → ctl.ref_* (seqlock) + レイテンシ値 */
  updateRef(): void {
    const ctx = this.ctx;
    if (!ctx || !this.i32) return;
    const ts = ctx.getOutputTimestamp();
    this.st("base_latency_us", Math.round((ctx.baseLatency || 0) * 1e6));
    this.st("out_latency_us", Math.round(this.outLat(ctx) * 1e6));
    if (!ts.performanceTime || ts.contextTime === undefined) return;
    const epochMs = performance.timeOrigin + ts.performanceTime;
    this.opts.refLog?.push({ ctxTime: ts.contextTime, epochMs });
    // getOutputTimestamp は ±数 ms ジッタがあるため、直近 16 点の最小二乗直線 (ctx→epoch) で平滑化して公開
    this.refPts.push({ x: ts.contextTime, y: epochMs });
    if (this.refPts.length > 16) this.refPts.shift();
    let ctxRef = ts.contextTime, epochRef = epochMs;
    const n = this.refPts.length;
    if (n >= 4) {
      const x0 = this.refPts[0].x, y0 = this.refPts[0].y;
      let sx = 0, sy = 0, sxx = 0, sxy = 0;
      for (const p of this.refPts) { const x = p.x - x0, y = p.y - y0; sx += x; sy += y; sxx += x * x; sxy += x * y; }
      const d = n * sxx - sx * sx;
      if (d > 0) {
        const slope = (n * sxy - sx * sy) / d, icpt = (sy - slope * sx) / n;
        ctxRef = ts.contextTime; epochRef = y0 + icpt + slope * (ts.contextTime - x0);
      }
    }
    const i = this.i32;
    Atomics.add(i, this.ix("ref_seq"), 1);
    this.i64f[0] = ctxRef;
    Atomics.store(i, this.ix("ref_ctx_time_bits"), this.i64u[0] | 0);
    Atomics.store(i, this.ix("ref_ctx_time_bits") + 1, this.i64u[1] | 0);
    this.i64f[0] = epochRef;
    Atomics.store(i, this.ix("ref_epoch_ms_bits"), this.i64u[0] | 0);
    Atomics.store(i, this.ix("ref_epoch_ms_bits") + 1, this.i64u[1] | 0);
    Atomics.add(i, this.ix("ref_seq"), 1);
  }

  /** producer の起床統計 (ctl の wake_hist[6] / wake_count / wait_timeouts) */
  producerStats(): ProducerStats {
    const base = this.ix("wake_hist");
    return {
      wake_hist: [0, 1, 2, 3, 4, 5].map((k) => Atomics.load(this.i32, base + k) >>> 0),
      wake_count: this.ld("wake_count") >>> 0,
      wait_timeouts: this.ld("wait_timeouts") >>> 0,
    };
  }

  /** ctl の統計スナップショット (テスト/診断用) */
  snapshot(): Record<string, number> {
    const o: Record<string, number> = {};
    for (const k of ["underruns", "silence_frames", "quanta", "in_overruns", "wl_state", "out_read", "out_write",
      "in_write", "in_read", "gen", "cb_count", "cb_late", "cb_max_us", "wake_count", "wait_timeouts", "in_underflows",
      "min_fill", "clock_jumps", "clock_jump_frames", "clock_skip_frames", "clock_dup_frames", "clock_jump_max", "clock_jump_max_q", "clock_first_q", "clock_last_q", "cb_max_q", "ring_frames", "buffer_frames", "depth", "sample_rate", "out_latency_us", "base_latency_us"] as FlaField[]) {
      o[k] = this.ld(k) >>> 0;
    }
    return o;
  }
}
