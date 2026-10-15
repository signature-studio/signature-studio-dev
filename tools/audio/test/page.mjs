// shim テストページ: URL クエリで構成を受け取り、wasm (fla_test) + FlAudioShim を起動して結果を window.__done (Promise) に返す。
import { FlAudioShim } from "./js/audio-shim.js";
import { FlAudioInput } from "./js/audio-input.js";

const q = new URLSearchParams(location.search);
const cfg = {
  api: q.get("api") ?? "asio",
  mode: q.get("mode") ?? "sine",
  buf: +(q.get("buf") ?? 256),
  depth: +(q.get("depth") ?? 2),
  secs: +(q.get("secs") ?? 10),
  sr: +(q.get("sr") ?? 48000),
  stress: +(q.get("stress") ?? 0),
  work_us: +(q.get("work_us") ?? 0),
  hiccup_ms: +(q.get("hiccup_ms") ?? 0),
  hiccup_every: +(q.get("hiccup_every") ?? 0),
  hiccup_stop_ms: +(q.get("hiccup_stop_ms") ?? 0), // >0: この時間以降は hiccup を止める (T 減衰の検証)
  timeinfo: +(q.get("timeinfo") ?? 0),
  sr_after: +(q.get("sr_after") ?? 0),
  burst_floor: +(q.get("burst_floor") ?? 0),
  ds_fmt: q.get("ds_fmt") ?? "pcm16",   // api=ds*: pcm16 | f32 (FL の primary SetFormat 組立の 2 経路)
  ds_mode: q.get("ds_mode") ?? "poll",  // poll | notify
  ds_size: +(q.get("ds_size") ?? 16384),
  input: q.get("input") ?? "none", // noise | gum | ui (FlAudioInput 経由)
  panel: +(q.get("panel") ?? 0),   // 1: ASIO controlPanel を呼ぶ (ui 入力: 別デバイスへ切替える UI 代替を登録)
  panel_ui: q.get("panel_ui") !== "0", // 0: controlPanel 未登録 (NotPresent 経路)
  lose: q.get("lose") === "1",     // 中間で入力 track の ended を発生 (デバイス喪失)
  jank: q.get("jank") === "1",     // main thread を 30ms/100ms ブロック
  suspend: q.get("suspend") === "1", // 中間で ctx.suspend()/resume()
  olat_zero_ms: +(q.get("olat_zero_ms") ?? 0), // >0: 最初の呼出から N ms の間 outputLatency=0 を返す (起動直後 0 の再現)
  olat_wait_ms: q.has("olat_wait_ms") ? +q.get("olat_wait_ms") : undefined, // ATTACH の待ち上限 (0 = 待たない旧挙動)
};
const logEl = document.getElementById("log");
const log = (s) => { logEl.textContent += s + "\n"; console.log(s); };

function noiseBuffer(ctx, seconds) {
  const n = Math.floor(ctx.sampleRate * seconds);
  const b = ctx.createBuffer(2, n, ctx.sampleRate);
  let s = 12345;
  for (let c = 0; c < 2; c++) {
    const d = b.getChannelData(c);
    for (let i = 0; i < n; i++) { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; d[i] = ((s >>> 8) / 8388608 - 1) * 0.5; }
  }
  return b;
}

window.__done = new Promise((resolveAll, rejectAll) => {
  let shim = null;
  const stderr = [];
  window.Module = {
    onAbort: (what) => setTimeout(() => resolveAll({ aborted: true, what: String(what), stderr, cfg }), 200),
    arguments: [
      `api=${cfg.api}`, `mode=${cfg.mode}`, `buf=${cfg.buf}`, `depth=${cfg.depth}`, `secs=${cfg.secs}`, `sr=${cfg.sr}`,
      `stress=${cfg.stress}`, `work_us=${cfg.work_us}`, `hiccup_ms=${cfg.hiccup_ms}`, `hiccup_every=${cfg.hiccup_every}`, `hiccup_stop_ms=${cfg.hiccup_stop_ms}`, `timeinfo=${cfg.timeinfo}`, `sr_after=${cfg.sr_after}`,
      `burst_floor=${cfg.burst_floor}`, `panel=${cfg.panel}`, `ds_fmt=${cfg.ds_fmt}`, `ds_mode=${cfg.ds_mode}`, `ds_size=${cfg.ds_size}`,
    ],
    print: (t) => log("[wasm] " + t),
    printErr: (t) => { stderr.push(String(t)); log("[wasm!] " + t); if (String(t).includes("FAIL-FAST")) setTimeout(() => resolveAll({ aborted: true, what: "fail-fast", stderr, cfg }), 500); },
    onRuntimeInitialized: () => {
      const M = window.Module;
      const api = {
        getBuffer: () => M.wasmMemory.buffer,
        ctlPtr: () => M._fla_ctl_ptr(),
        layoutCount: () => M._fla_layout_count(),
        layoutOff: (i) => M._fla_layout_off(i),
        layoutName: (i) => M.UTF8ToString(M._fla_layout_name(i)),
      };
      let ctxInfo = {};
      let zeroT0;
      const refLog = [];
      window.__refLog = refLog;
      const ui = { events: [], devices: [], panelOpened: 0, switched: null, labels: [] };
      let input = null;
      if (cfg.input === "ui" || cfg.input === "ui_denied") {
        // ui_denied: getUserMedia が NotAllowedError で拒否される環境 (権限ダイアログで「ブロック」)。出力は継続する必要がある
        const denied = { getUserMedia: () => Promise.reject(new DOMException("denied", "NotAllowedError")), enumerateDevices: async () => [], addEventListener() {}, removeEventListener() {} };
        input = new FlAudioInput({ log, storage: null, mediaDevices: cfg.input === "ui_denied" ? denied : undefined });
        input.on((e) => ui.events.push(e.type === "devices" ? { type: "devices", n: e.devices.length } : e));
        window.__input = input;
      }
      shim = new FlAudioShim(api, {
        workletUrl: "worklets/fl-audio-worklet.js",
        input: input ?? undefined,
        controlPanel: cfg.panel && cfg.panel_ui ? async () => {
          ui.panelOpened++;
          // パネル UI の代替: 権限状態 → デバイス一覧 → 既定以外の最初のデバイスを選択 (ライブ切替)
          ui.permission = await input.permission();
          ui.devices = (await input.listDevices()).map((d) => d.label);
          const cur = input.activeTrack?.label;
          ui.labels.push(cur);
          ui.permission_after = await input.requestPermission();
          const alt = (await input.listDevices()).find((d) => d.deviceId !== "default" && d.label && d.label !== cur);
          if (alt) { await input.select(alt.deviceId); ui.switched = input.activeTrack?.label ?? null; ui.labels.push(ui.switched); }
        } : undefined,
        refLog,
        log,
        outputLatencyWaitMs: cfg.olat_wait_ms,
        readOutputLatency: cfg.olat_zero_ms > 0
          ? (ctx) => { zeroT0 ??= performance.now(); return performance.now() - zeroT0 < cfg.olat_zero_ms ? 0 : ctx.outputLatency; }
          : undefined,
        captureFactory: (outCh, inCh) => {
          const frames = Math.ceil((cfg.secs * cfg.sr + 8192) / 128) * 128;
          const bytes = 64 + frames * (outCh + inCh) * 4 + (frames / 128) * 4;
          return { sab: new SharedArrayBuffer(bytes), frames, outCh, inCh };
        },
        onNode: async (ctx, node) => {
          ctxInfo = { sampleRate: ctx.sampleRate, baseLatency: ctx.baseLatency, outputLatency: ctx.outputLatency };
          if (cfg.input === "noise") {
            const src = ctx.createBufferSource();
            src.buffer = noiseBuffer(ctx, 1);
            src.loop = true;
            src.connect(node);
            src.start();
          } else if (cfg.input === "ui" || cfg.input === "ui_denied") {
            // 実運用経路: FlAudioShim が input.connect() を呼ぶ (onNode の後)
          } else if (cfg.input === "gum") {
            const ms = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 2 } });
            ctxInfo.gumTracks = ms.getAudioTracks().map((t) => ({ label: t.label, settings: t.getSettings() }));
            ctx.createMediaStreamSource(ms).connect(node);
          }
        },
      });
      shim.attach();
      window.__shim = shim;
      if (cfg.jank) {
        setInterval(() => { const t = performance.now(); while (performance.now() - t < 30) { /* busy */ } }, 100);
      }
      if (cfg.lose) {
        setTimeout(() => { const t = input?.activeTrack; ui.lostTrack = t?.label ?? null; t?.dispatchEvent(new Event("ended")); }, cfg.secs * 500);
      }
      if (cfg.suspend) {
        setTimeout(async () => { await shim.context?.suspend(); setTimeout(() => shim.context?.resume(), 500); }, cfg.secs * 500);
      }
      // 完了待ち
      const donePtr = () => new Int32Array(M.wasmMemory.buffer, M._fla_test_done_ptr(), 1);
      (async () => {
        const deadline = performance.now() + (cfg.secs + 40) * 1000;
        for (;;) {
          const d = donePtr();
          if (Atomics.load(d, 0) !== 0) break;
          if (performance.now() > deadline) { rejectAll(new Error("test timeout")); return; }
          const r = Atomics.waitAsync(d, 0, 0, 1000);
          if (r.async) await r.value;
        }
        const code = Atomics.load(donePtr(), 0);
        const resPtr = M._fla_test_result_ptr();
        const text = M.UTF8ToString(resPtr);
        let result;
        try { result = JSON.parse(text); } catch (e) { rejectAll(new Error("bad result json: " + text)); return; }
        result.exit = code;
        result.ctx = ctxInfo;
        if (input) {
          ui.controlPanelCalls = shim.controlPanelCalls;
          result.ui = ui;
        }
        result.snapshot = shim.snapshot();
        result.workletErrors = shim.workletErrors;
        result.clockJumpLog = shim.clockJumpLog;
        result.cfg = cfg;
        if (refLog.length > 4) { // contextTime(s) vs epochMs の傾き: 1.0 ならオーディオクロック = 壁時計
          const n = refLog.length, x0 = refLog[0].epochMs, y0 = refLog[0].ctxTime;
          let sx = 0, sy = 0, sxx = 0, sxy = 0;
          for (const r of refLog) { const x = (r.epochMs - x0) / 1000, y = r.ctxTime - y0; sx += x; sy += y; sxx += x * x; sxy += x * y; }
          result.ref_slope = { n, ctx_per_wall: (n * sxy - sx * sy) / (n * sxx - sx * sx) };
        }
        if (shim.lastCapture) result.verify = verify(shim.lastCapture, cfg, result);
        resolveAll(result);
      })();
    },
  };
  const s = document.createElement("script");
  s.src = "fla_test.js";
  document.body.appendChild(s);
});

// ---- 出力/入力ダンプの検証 --------------------------------------------------------------------
function verify(capSpec, cfg, result) {
  const hdr = new Int32Array(capSpec.sab, 0, 16);
  const frames = capSpec.frames;
  const covered = Atomics.load(hdr, 0);
  const out = new Float32Array(capSpec.sab, 64, frames * capSpec.outCh);
  const inn = new Float32Array(capSpec.sab, 64 + frames * capSpec.outCh * 4, frames * capSpec.inCh);
  const fill = new Int32Array(capSpec.sab, 64 + frames * (capSpec.outCh + capSpec.inCh) * 4, frames / 128);
  const sr = result.ctx.sampleRate;
  const v = { covered_frames: covered, sr, gen_inits: Atomics.load(hdr, 2), playing_quanta: Atomics.load(hdr, 3), first_underrun_q: Atomics.load(hdr, 4), last_underrun_q: Atomics.load(hdr, 5), underrun_events: Atomics.load(hdr, 6),
    audio_thread_gap_ms_hist: { '0': Atomics.load(hdr, 8), '1-5': Atomics.load(hdr, 9), '6-12': Atomics.load(hdr, 10), '13-20': Atomics.load(hdr, 11), '21-40': Atomics.load(hdr, 12), '>40': Atomics.load(hdr, 13), max: Atomics.load(hdr, 14) } };
  if (q.get("dump")) v.dump = Array.from(out.subarray(0, +q.get("dump")));
  { // 非ゼロ区間の列挙 (診断)
    const spans = []; let st = -1;
    for (let p = 0; p <= covered && spans.length < 12; p++) {
      const nz = p < covered && out[p] !== 0;
      if (nz && st < 0) st = p; else if (!nz && st >= 0) { spans.push([st, p - st, out[st]]); st = -1; }
    }
    v.spans = spans;
  }
  const nq = Math.floor(covered / 128);
  const start = Math.min(nq, 8);
  let fmin = 1e9, fmax = -1, fsum = 0, cnt = 0;
  for (let k = start; k < nq; k++) { const f = fill[k]; fmin = Math.min(fmin, f); fmax = Math.max(fmax, f); fsum += f; cnt++; }
  v.device_fill = { min: fmin, max: fmax, avg: cnt ? fsum / cnt : 0, unit: "frames (リング充填, worklet 消費直前)" };
  const ch0 = out.subarray(0, frames), ch1 = out.subarray(frames, 2 * frames);
  if (cfg.api === "ds" && cfg.ds_fmt === "pcm16") {
    // 16bit PCM 経路: クライアントは int16 ランプ (n%30000+1, 右は符号反転) を書く → shim は v/32768 の float32 へ変換 (2 の冪除算なので厳密)
    let ok = 0, firstBad = -1, bad = 0;
    for (let p = 0; p < covered; p++) {
      const e0 = Math.fround(((p % 30000) + 1) / 32768);
      if (ch0[p] === e0 && ch1[p] === -e0) ok++;
      else { bad++; if (firstBad < 0) firstBad = p; }
    }
    v.ramp16 = { frames_checked: covered, bit_exact: ok, mismatches: bad, first_mismatch_frame: firstBad };
  } else if (cfg.mode === "ramp") {
    let ok = 0, firstBad = -1, bad = 0;
    for (let p = 0; p < covered; p++) {
      const e0 = (p & 0xFFFFFF) + 1; // fla_test.c のランプは 24bit (f32 の厳密整数域) で巻き戻る: 2^24 f = 349.5 s @48k。30 分ソークは巻き戻しを跨ぐ
      if (ch0[p] === e0 && ch1[p] === -e0) ok++;
      else { bad++; if (firstBad < 0) firstBad = p; }
    }
    v.ramp = { frames_checked: covered, bit_exact: ok, mismatches: bad, first_mismatch_frame: firstBad };
    // underrun 後の連続性: out[p] == ramp[p - S] (S = underrun で挿入された無音フレーム数) が末尾領域で成立するか
    const S = result.stats.silence_frames, lo = Math.max(0, covered - 20000), hi = Math.max(lo, covered - 3000);
    let tail_ok = 0, tail_n = 0;
    for (let p = lo; p < hi; p++) { tail_n++; const e = ((p - S) & 0xFFFFFF) + 1; if (ch0[p] === e && ch1[p] === -e) tail_ok++; }
    v.ramp.tail_shift_exact = { silence_S: S, checked: tail_n, exact: tail_ok };
  } else if (cfg.mode === "sine") {
    let maxErr = 0, peak = 0, ss = 0, bad = 0;
    for (let p = 0; p < covered; p++) {
      const e0 = 0.5 * Math.sin(2 * Math.PI * 440 * p / sr);
      const e1 = 0.5 * Math.sin(2 * Math.PI * 660 * p / sr);
      const d = Math.max(Math.abs(ch0[p] - e0), Math.abs(ch1[p] - e1));
      if (d > maxErr) maxErr = d;
      if (d > 1e-5) bad++;
      peak = Math.max(peak, Math.abs(ch0[p]));
      ss += ch0[p] * ch0[p];
    }
    // 無音ラン (連続 16 サンプル以上の厳密 0: 正弦のゼロ交差では起きない) = ドロップアウト
    let runs = 0, run = 0;
    for (let p = 0; p < covered; p++) { if (ch0[p] === 0) { run++; if (run === 16) runs++; } else run = 0; }
    v.sine = { frames_checked: covered, max_abs_err: maxErr, samples_over_1e5: bad, peak, rms: Math.sqrt(ss / covered), expect_rms: 0.5 / Math.SQRT2, zero_runs_ge16: runs };
  } else if (cfg.mode === "loop" && capSpec.inCh > 0) {
    // 入力→出力 (worklet 同一クロック上のフレーム番号) の遅延 = 相互相関ピーク
    const i0 = inn.subarray(0, frames);
    const W = Math.min(sr, Math.max(0, covered - sr)); // 1 s 窓
    const base = Math.min(Math.floor(sr / 2), Math.max(0, covered - W - 9000));
    const maxLag = 8192;
    let best = -1, bestLag = -1, e_in = 0;
    for (let k = 0; k < W; k++) e_in += i0[base + k] * i0[base + k];
    const lags = [];
    for (let lag = 0; lag <= maxLag; lag++) {
      let s = 0, eo = 0;
      for (let k = 0; k < W; k++) { const o = ch0[base + k + lag]; s += i0[base + k] * o; eo += o * o; }
      const nc = e_in > 0 && eo > 0 ? s / Math.sqrt(e_in * eo) : 0;
      if (nc > best) { best = nc; bestLag = lag; }
      if (lag < 3) lags.push(nc);
    }
    v.loop = { window: W, base, best_norm_corr: best, lag_frames: bestLag, lag_ms: bestLag * 1000 / sr, input_rms: Math.sqrt(e_in / W) };
  }
  return v;
}
