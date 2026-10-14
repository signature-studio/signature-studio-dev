/**
 * FL audio shim — AudioWorkletProcessor (128 フレーム固定)。
 *
 * wasm 線形メモリ (SharedArrayBuffer) 上の fla_ctl_t / planar f32 リングを直接読み書きする。
 * 設計: tools/audio/docs/PROTOCOL.md。オフセットは C ヘッダ (flaudio.h) が単一の真実で、
 * コントローラが wasm の fla_layout_off() から取得して processorOptions.layout で渡す (ここでは固定値を持たない)。
 *
 * ここで行うこと:
 *  - 出力: リングから 128 フレーム read (不足は無音 + declick, underrun 計上, rebuffer 状態へ)
 *  - 入力: inputs[0] を入力リングへ write (溢れは破棄して in_overruns 計上)
 *  - クロック: dev_frames / currentTime を seqlock 付きで公開 (デバイスクロック master)
 *  - producer の起床: out_read が wake_target に達したら Atomics.notify
 *  - (任意) テスト用キャプチャ: processorOptions.capture の SAB へ出力/入力/ring 充填をダンプ
 */
const WL_IDLE = 0, WL_BUFFERING = 1, WL_PLAYING = 2;
const F_DECLICK = 1, F_INPUT = 2;
const FADE = 32;
const Q = 128;

class FlShimProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super(options);
    const o = options.processorOptions;
    this.L = o.layout;
    this.buffer = o.buffer;
    this.ctlPtr = o.ctlPtr;
    this.i32 = new Int32Array(this.buffer, this.ctlPtr, 96);
    this.ix = {};
    for (const k of Object.keys(this.L)) this.ix[k] = this.L[k] >> 2;
    this.f64 = new Float64Array(1);
    this.f64u = new Uint32Array(this.f64.buffer);
    this.gen = -1;
    this.out = null; this.in = null;
    this.last = new Float32Array(8);
    this.fadeIn = 0;
    this.everUnderrun = false;
    this.cap = null;
    if (o.capture) {
      const c = o.capture;
      this.cap = {
        ring: !!c.ring, hdr: new Int32Array(c.sab, 0, 16), frames: c.frames, och: c.outCh, ich: c.inCh,
        out: new Float32Array(c.sab, 64, c.frames * c.outCh),
        in: new Float32Array(c.sab, 64 + c.frames * c.outCh * 4, c.frames * c.inCh),
        fill: new Int32Array(c.sab, 64 + c.frames * (c.outCh + c.inCh) * 4, c.frames / Q),
      };
    }
    this.playStart = 0;
    this.q = 0;
    this.prevFrame = -1;
    this.prevMs = 0;
    this.burstPrevMs = 0;
    this.burstRun = 0;
    this.err = false;
    this.port.postMessage({ type: "ready", sampleRate, ctlPtr: this.ctlPtr });
  }

  refreshRings() {
    const i = this.i32, x = this.ix;
    this.ringFrames = Atomics.load(i, x.ring_frames);
    this.mask = Atomics.load(i, x.ring_mask);
    this.och = Atomics.load(i, x.out_ch);
    this.ich = Atomics.load(i, x.in_ch);
    this.flags = Atomics.load(i, x.flags);
    this.rebuf = Atomics.load(i, x.rebuffer_frames);
    const op = Atomics.load(i, x.out_ring_ptr), ip = Atomics.load(i, x.in_ring_ptr);
    this.out = new Float32Array(this.buffer, op, this.ringFrames * this.och);
    this.in = this.ich ? new Float32Array(this.buffer, ip, this.ringFrames * this.ich) : null;
  }

  publishClock(frame, time) {
    const i = this.i32, x = this.ix;
    Atomics.add(i, x.clock_seq, 1);
    this.f64[0] = time;
    Atomics.store(i, x.dev_frames, frame >>> 0);
    Atomics.store(i, x.dev_frames + 1, Math.floor(frame / 4294967296) | 0);
    Atomics.store(i, x.dev_ctx_time_bits, this.f64u[0] | 0);
    Atomics.store(i, x.dev_ctx_time_bits + 1, this.f64u[1] | 0);
    Atomics.add(i, x.clock_seq, 1);
  }

  process(inputs, outputs) {
    try { this.run(inputs, outputs); } catch (e) {
      if (!this.err) { this.err = true; this.port.postMessage({ type: "error", message: String(e && e.stack || e) }); }
    }
    return true;
  }

  run(inputs, outputs) {
    const i = this.i32, x = this.ix;
    const outp = outputs[0];
    const frame = currentFrame, time = currentTime;
    if (this.prevFrame >= 0 && frame !== this.prevFrame + Q) {
      const d = (frame - this.prevFrame - Q) | 0;   // >0: 描画されなかったフレーム (実スキップ), <0: 重複・後退 (符号付き合計では相殺しうるので別計上)
      const nj = Atomics.add(i, x.clock_jumps, 1) + 1;
      Atomics.add(i, x.clock_jump_frames, d);
      const qv = Atomics.load(i, x.quanta) | (d < 0 ? 0x80000000 : 0);   // 位置: 最初と直近の jump (bit31 = 負)
      if (nj === 1) Atomics.store(i, x.clock_first_q, qv);
      Atomics.store(i, x.clock_last_q, qv);
      if (nj <= 256) this.port.postMessage({ type: "clock_jump", q: Atomics.load(i, x.quanta), d, frame, prev: this.prevFrame, ms: Date.now(),
        ct: time, pn: typeof performance !== "undefined" ? performance.now() : -1, cb: Atomics.load(i, x.cb_count) });   // 全件の位置 (上限 256 件)。ct = currentTime, pn = performance.now() (不可なら -1), cb = producer の bufferSwitch 通し番号
      if (d > 0) Atomics.add(i, x.clock_skip_frames, d); else Atomics.add(i, x.clock_dup_frames, -d);
      if (Math.abs(d) > Atomics.load(i, x.clock_jump_max)) {
        Atomics.store(i, x.clock_jump_max, Math.abs(d));
        Atomics.store(i, x.clock_jump_max_q, Atomics.load(i, x.quanta));
      }
    }
    this.prevFrame = frame;
    {   // バースト長の観測: Date.now() 差 <=1ms で連続する process() の総フレーム数の最大値を burst_obs に公開
      const nowb = Date.now();
      if (this.burstPrevMs > 0 && nowb - this.burstPrevMs <= 1) this.burstRun += Q;
      else this.burstRun = Q;
      this.burstPrevMs = nowb;
      if (this.burstRun > Atomics.load(i, x.burst_obs)) Atomics.store(i, x.burst_obs, this.burstRun);
    }
    if (this.cap) {   // オーディオスレッドの呼出間隔 (Date.now, ms) ヒストグラム: hdr[8..13] = 0 / 1-5 / 6-12 / 13-20 / 21-40 / >40 ms, hdr[14] = max
      const now = Date.now();
      if (this.prevMs > 0) {
        const g = now - this.prevMs, h = this.cap.hdr;
        Atomics.add(h, 8 + (g < 1 ? 0 : g <= 5 ? 1 : g <= 12 ? 2 : g <= 20 ? 3 : g <= 40 ? 4 : 5), 1);
        if (g > Atomics.load(h, 14)) Atomics.store(h, 14, g);
      }
      this.prevMs = now;
    }
    this.publishClock(frame, time);
    const quanta = Atomics.add(i, x.quanta, 1) + 1;
    {
      const tick = Atomics.load(i, x.tick_target);
      if (((frame - tick) | 0) >= 0) Atomics.notify(i, x.quanta, 0x7fffffff);
    }
    const go = Atomics.load(i, x.go);
    let wl = Atomics.load(i, x.wl_state);
    if (!go) {
      for (const ch of outp) ch.fill(0);
      if (wl !== WL_IDLE) {
        Atomics.store(i, x.wl_state, WL_IDLE);
        Atomics.notify(i, x.wl_state, 0x7fffffff);
      }
      return;
    }
    const gen = Atomics.load(i, x.gen);
    if (gen !== this.gen) {
      this.gen = gen;
      this.refreshRings();
      this.everUnderrun = false; this.everPlayed = false; this.fadeIn = 0;
      this.last.fill(0);
      this.playStart = frame;
      this.q = 0;
      Atomics.store(i, x.clock_jumps, 0);
      Atomics.store(i, x.clock_jump_frames, 0);
      Atomics.store(i, x.clock_skip_frames, 0);
      Atomics.store(i, x.clock_dup_frames, 0);
      Atomics.store(i, x.clock_jump_max, 0);
      Atomics.store(i, x.clock_jump_max_q, 0);
      Atomics.store(i, x.clock_first_q, 0);
      Atomics.store(i, x.clock_last_q, 0);
      Atomics.store(i, x.play_start_frame, frame >>> 0);
      Atomics.store(i, x.play_start_frame + 1, Math.floor(frame / 4294967296) | 0);
      Atomics.store(i, x.wl_state, WL_BUFFERING);
      wl = WL_BUFFERING;
      if (this.cap) { Atomics.store(this.cap.hdr, 0, 0); Atomics.store(this.cap.hdr, 1, gen); Atomics.add(this.cap.hdr, 2, 1); }
    }
    const och = this.och, mask = this.mask, ring = this.ringFrames;
    const p = this.q * Q;   // この quantum の run 内オフセット (process() 呼出ベース; ブラウザのスキップと独立にデータ連続性を検証できる)
    this.q++;

    // ---- 入力 (先に write: producer は out_read で起床するため in_write を先に進める) ----
    if (this.in) {
      const inp = inputs[0] || [];
      const iw = Atomics.load(i, x.in_write), ir = Atomics.load(i, x.in_read);
      if (((iw - ir) | 0) + Q > ring) {
        Atomics.add(i, x.in_overruns, 1);
      } else {
        const pos = iw & mask;
        for (let c = 0; c < this.ich; c++) {
          const src = inp[c];
          const dst = this.in.subarray(c * ring, (c + 1) * ring);
          const first = Math.min(Q, ring - pos);
          if (src) { dst.set(src.subarray(0, first), pos); if (first < Q) dst.set(src.subarray(first, Q), 0); }
          else { dst.fill(0, pos, pos + first); if (first < Q) dst.fill(0, 0, Q - first); }
        }
        Atomics.store(i, x.in_write, (iw + Q) | 0);
      }
      if (this.capOk(p)) {
        for (let c = 0; c < this.cap.ich; c++) {
          const src = inp[c];
          if (src) this.capPut(this.cap.in, c * this.cap.frames, p, src);
        }
      }
    }

    // ---- 出力 ----
    const rd = Atomics.load(i, x.out_read), wr = Atomics.load(i, x.out_write);
    const avail = (wr - rd) | 0;
    if (this.capOk(p)) this.cap.fill[this.cap.ring ? (p >> 7) % this.cap.fill.length : p >> 7] = avail;
    let consumed = 0;
    let produced = 0;   // この quantum で実音声を書いたフレーム数 (declick 起点)

    if (wl === WL_BUFFERING) {
      const need = this.everPlayed ? this.rebuf : Math.min(this.rebuf, Q);
      if (avail >= need) { wl = WL_PLAYING; Atomics.store(i, x.wl_state, WL_PLAYING); this.everPlayed = true; if (this.everUnderrun) this.fadeIn = FADE; }
    }
    if (wl === WL_PLAYING) {
      consumed = avail >= Q ? Q : (avail > 0 ? avail : 0);
      if (consumed > 0) {
        const pos = rd & mask;
        const first = Math.min(consumed, ring - pos);
        for (let c = 0; c < outp.length; c++) {
          const dst = outp[c];
          if (c < och) {
            const base = c * ring;
            dst.set(this.out.subarray(base + pos, base + pos + first), 0);
            if (consumed > first) dst.set(this.out.subarray(base, base + consumed - first), first);
          } else dst.fill(0, 0, consumed);
        }
        produced = consumed;
        if (this.cap) Atomics.add(this.cap.hdr, 3, 1);
        const nr = (rd + consumed) | 0;
        Atomics.store(i, x.out_read, nr);
        const wt = Atomics.load(i, x.wake_target);
        if (((nr - wt) | 0) >= 0) {
          // one-shot: 目標を到達不能値へ退避 (producer が再武装していれば CAS が失敗して上書きしない)
          if (Atomics.compareExchange(i, x.wake_target, wt, (wt + 0x40000000) | 0) === wt) {
            Atomics.store(i, x.notify_ms, Date.now() | 0);
            Atomics.notify(i, x.out_read, 0x7fffffff);
          }
        }
      }
      if (consumed < Q) {
        // underrun: 不足分は無音、declick、rebuffer 状態へ
        Atomics.add(i, x.underruns, 1);
        if (this.cap) { const h = this.cap.hdr; if (Atomics.load(h, 6) === 0) Atomics.store(h, 4, p / Q); Atomics.store(h, 5, p / Q); Atomics.add(h, 6, 1); }
        Atomics.add(i, x.silence_frames, Q - consumed);
        this.everUnderrun = true;
        Atomics.store(i, x.wl_state, WL_BUFFERING);
        wl = WL_BUFFERING;
        for (let c = 0; c < outp.length; c++) {
          const dst = outp[c];
          const lastv = consumed > 0 ? dst[consumed - 1] : this.last[c];
          const n = (this.flags & F_DECLICK) ? Math.min(FADE, Q - consumed) : 0;
          for (let k = 0; k < n; k++) dst[consumed + k] = lastv * (1 - (k + 1) / FADE);
          dst.fill(0, consumed + n, Q);
        }
      }
      if (this.fadeIn > 0 && consumed > 0) {
        const n = Math.min(this.fadeIn, consumed), start = FADE - this.fadeIn;
        for (let c = 0; c < outp.length; c++) for (let k = 0; k < n; k++) outp[c][k] *= (start + k + 1) / FADE;
        this.fadeIn -= n;
      }
    } else {
      for (const ch of outp) ch.fill(0);
      Atomics.add(i, x.silence_frames, this.everPlayed ? Q : 0);
    }
    for (let c = 0; c < outp.length && c < this.last.length; c++) this.last[c] = outp[c][Q - 1];
    if (this.capOk(p)) {
      for (let c = 0; c < this.cap.och; c++) if (outp[c]) this.capPut(this.cap.out, c * this.cap.frames, p, outp[c]);
      Atomics.store(this.cap.hdr, 0, p + Q);
    }
    void quanta; void produced;
  }

  capOk(p) { return !!this.cap && p >= 0 && (this.cap.ring || p + Q <= this.cap.frames); }

  // ring 時は絶対フレーム p を frames で剰余した位置へ書く (照合側は未照合区間を ring 容量内で読む)
  capPut(a, off, p, src) {
    const n = this.cap.frames;
    if (!this.cap.ring) { a.set(src, off + p); return; }
    const s = p % n, first = Math.min(Q, n - s);
    a.set(src.subarray(0, first), off + s);
    if (first < Q) a.set(src.subarray(first, Q), off);
  }
}

registerProcessor("fl-audio-shim", FlShimProcessor);

/** OPEN 時の較正用: 96 quanta の間に観測した最長バースト (Date.now 差 <=1ms で連続する process() の総フレーム数) を返して終了 */
class FlBurstProbe extends AudioWorkletProcessor {
  constructor() { super(); this.n = 0; this.prev = 0; this.run = 0; this.max = 0; }
  process() {
    const now = Date.now();
    this.run = this.prev > 0 && now - this.prev <= 1 ? this.run + Q : Q;
    this.prev = now;
    if (this.run > this.max) this.max = this.run;
    if (++this.n === 96) this.port.postMessage({ type: "burst", max: this.max });
    return this.n < 96;
  }
}
registerProcessor("fl-burst-probe", FlBurstProbe);
