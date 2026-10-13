// COM 経由キャプチャの分割照合 (AU-19 / #1358)。ブラウザ・node 共用 (import 無し)。
// キャプチャ SAB は固定容量 N フレームの ring (fl-audio-worklet.js の capPut): 絶対フレーム p は位置 p % N へ書かれる。
// N は全長以上なら一括と同じ配置になる (p % N = p)。照合は未照合区間 [done, covered) を step() ごとに畳み込み、
// 最後の finish() で残りを畳む。区間 1 本で通した一括照合と同一の結果になることを selftest で確認する。

export const CAP_Q = 128;
export const CAP_RING_FRAMES = 1 << 21;   // 43.7 s @48k。ソーク時も SAB は約 16 MiB に抑える

// 定義: 64 + N×(outCh+inCh)×4 + (N/128)×4 B
export function capSpecBytes(N, outCh, inCh) { return 64 + N * (outCh + inCh) * 4 + (N / CAP_Q) * 4; }

export class ChunkVerifier {
  constructor(spec, opts) {
    this.N = spec.frames; this.och = spec.outCh; this.ich = spec.inCh;
    this.mode = opts.mode; this.sr = opts.sr; this.ring = !!opts.ring;
    this.hdr = new Int32Array(spec.sab, 0, 16);
    this.out = new Float32Array(spec.sab, 64, this.N * this.och);
    this.fill = new Int32Array(spec.sab, 64 + this.N * (this.och + this.ich) * 4, this.N / CAP_Q);
    this.done = 0; this.doneQ = 0; this.fail = null;
    this.fmin = 1e9; this.fmax = -1; this.fsum = 0; this.fcnt = 0;
    this.ok = 0; this.bad = 0; this.firstBad = -1;
    this.maxErr = 0; this.over = 0; this.peak = 0; this.ss = 0; this.run = 0; this.zeroRuns = 0;
  }

  step() {
    const covered = Atomics.load(this.hdr, 0);
    if (covered < this.done) { this.fail ??= `covered が巻き戻った (done=${this.done} covered=${covered})`; return; }
    // ring は未照合区間が容量の半分を超えると上書きされ始める (照合遅延の検出)
    if (this.ring && covered - this.done > this.N / 2) { this.fail ??= `照合遅延: 未照合 ${covered - this.done}f > N/2`; return; }
    const N = this.N, out = this.out, sr = this.sr, end = covered;
    for (let p = this.done; p < end; p++) {
      const i = p % N;
      const a = out[i], b = out[N + i];
      if (this.mode === "ramp") {
        const e0 = (p & 0xFFFFFF) + 1;
        if (a === e0 && b === -e0) this.ok++;
        else { this.bad++; if (this.firstBad < 0) this.firstBad = p; }
      } else {
        const e0 = 0.5 * Math.sin(2 * Math.PI * 440 * p / sr), e1 = 0.5 * Math.sin(2 * Math.PI * 660 * p / sr);
        const d = Math.max(Math.abs(a - e0), Math.abs(b - e1));
        if (d > this.maxErr) this.maxErr = d;
        if (d > 1e-5) this.over++;
        this.peak = Math.max(this.peak, Math.abs(a));
        this.ss += a * a;
        if (a === 0) { this.run++; if (this.run === 16) this.zeroRuns++; } else this.run = 0;
      }
    }
    const qEnd = Math.floor(end / CAP_Q), F = this.fill.length;
    for (let k = Math.max(this.doneQ, 8); k < qEnd; k++) {
      const v = this.fill[k % F];
      this.fmin = Math.min(this.fmin, v); this.fmax = Math.max(this.fmax, v); this.fsum += v; this.fcnt++;
    }
    this.doneQ = Math.max(this.doneQ, qEnd);
    this.done = end;
  }

  finish() { this.step(); return this.result(); }

  result() {
    const v = {
      covered_frames: this.done, sr: this.sr, underrun_events: Atomics.load(this.hdr, 6), fail: this.fail,
      device_fill: { min: this.fmin, max: this.fmax, avg: this.fcnt ? this.fsum / this.fcnt : 0 },
    };
    if (this.mode === "ramp") {
      v.ramp = { frames_checked: this.done, bit_exact: this.ok, mismatches: this.bad, first_mismatch_frame: this.firstBad };
    } else {
      v.sine = { frames_checked: this.done, max_abs_err: this.maxErr, samples_over_1e5: this.over, peak: this.peak,
        rms: Math.sqrt(this.ss / this.done), expect_rms: 0.5 / Math.SQRT2, zero_runs_ge16: this.zeroRuns };
    }
    return v;
  }
}
