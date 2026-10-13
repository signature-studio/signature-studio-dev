// COM アダプタ テストページ (tools/audio/test/page.mjs の流儀を踏襲 — ramp/sine 検証のみに簡略化)。
// com_test (wasm) を起動し、FlAudioShim を接続。結果 JSON を window.__done (Promise) へ返す。
import { FlAudioShim } from "./js/audio-shim.js";

const q = new URLSearchParams(location.search);
const cfg = {
  mode: q.get("mode") ?? "ramp",
  buf: +(q.get("buf") ?? 256),
  secs: +(q.get("secs") ?? 5),
  sr: +(q.get("sr") ?? 48000),
};
const logEl = document.getElementById("log");
const log = (s) => { logEl.textContent += s + "\n"; console.log(s); };

window.__done = new Promise((resolveAll, rejectAll) => {
  let shim = null;
  const stderr = [];
  window.Module = {
    onAbort: (what) => setTimeout(() => resolveAll({ aborted: true, what: String(what), stderr, cfg }), 200),
    arguments: [`mode=${cfg.mode}`, `buf=${cfg.buf}`, `secs=${cfg.secs}`, `sr=${cfg.sr}`],
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
      const refLog = [];
      shim = new FlAudioShim(api, {
        workletUrl: "worklets/fl-audio-worklet.js",
        refLog, log,
        captureFactory: (outCh, inCh) => {
          const frames = Math.ceil((cfg.secs * cfg.sr + 8192) / 128) * 128;
          const bytes = 64 + frames * (outCh + inCh) * 4 + (frames / 128) * 4;
          return { sab: new SharedArrayBuffer(bytes), frames, outCh, inCh };
        },
        onNode: async (ctx, node) => { ctxInfo = { sampleRate: ctx.sampleRate, baseLatency: ctx.baseLatency, outputLatency: ctx.outputLatency }; void node; },
      });
      shim.attach();
      window.__shim = shim;
      (async () => {
        const donePtr = () => new Int32Array(M.wasmMemory.buffer, M._com_test_done_ptr(), 1);
        // 余裕: 実行秒数 + max(40, 秒数×0.5)。120s soak (CAB-270) は wasm 側の emscripten_get_now() で 120s で抜けるため、
        // ここは main thread スタベの検出のみが役目。短シナリオの既存動作 (40s) は変えない。
        const slack = Math.max(40, Math.ceil(cfg.secs * 0.5));
        const deadline = performance.now() + (cfg.secs + slack) * 1000;
        for (;;) {
          const d = donePtr();
          if (Atomics.load(d, 0) !== 0) break;
          if (performance.now() > deadline) { rejectAll(new Error("test timeout")); return; }
          const r = Atomics.waitAsync(d, 0, 0, 1000);
          if (r.async) await r.value;
        }
        const code = Atomics.load(donePtr(), 0);
        let result;
        try { result = JSON.parse(M.UTF8ToString(M._com_test_result_ptr())); } catch (e) { rejectAll(new Error("bad result json")); return; }
        result.exit = code;
        result.ctx = ctxInfo;
        result.snapshot = shim.snapshot();
        result.workletErrors = shim.workletErrors;
        result.cfg = cfg;
        if (shim.lastCapture) result.verify = verify(shim.lastCapture, cfg, result);
        resolveAll(result);
      })();
    },
  };
  const s = document.createElement("script");
  s.src = "com_test.js";
  document.body.appendChild(s);
});

// ---- 出力ダンプの検証 (page.mjs の ramp/sine 判定と同一基準) ----
function verify(capSpec, cfg, result) {
  const hdr = new Int32Array(capSpec.sab, 0, 16);
  const frames = capSpec.frames;
  const covered = Atomics.load(hdr, 0);
  const out = new Float32Array(capSpec.sab, 64, frames * capSpec.outCh);
  const fill = new Int32Array(capSpec.sab, 64 + frames * capSpec.outCh * 4, frames / 128);
  const sr = result.ctx.sampleRate;
  const v = { covered_frames: covered, sr, underrun_events: Atomics.load(hdr, 6) };
  const nq = Math.floor(covered / 128);
  const start = Math.min(nq, 8);
  let fmin = 1e9, fmax = -1, fsum = 0, cnt = 0;
  for (let k = start; k < nq; k++) { fmin = Math.min(fmin, fill[k]); fmax = Math.max(fmax, fill[k]); fsum += fill[k]; cnt++; }
  v.device_fill = { min: fmin, max: fmax, avg: cnt ? fsum / cnt : 0 };
  const ch0 = out.subarray(0, frames), ch1 = out.subarray(frames, 2 * frames);
  if (cfg.mode === "ramp") {
    let ok = 0, firstBad = -1, bad = 0;
    for (let p = 0; p < covered; p++) {
      const e0 = (p & 0xFFFFFF) + 1;
      if (ch0[p] === e0 && ch1[p] === -e0) ok++;
      else { bad++; if (firstBad < 0) firstBad = p; }
    }
    v.ramp = { frames_checked: covered, bit_exact: ok, mismatches: bad, first_mismatch_frame: firstBad };
  } else {
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
    let runs = 0, run = 0;
    for (let p = 0; p < covered; p++) { if (ch0[p] === 0) { run++; if (run === 16) runs++; } else run = 0; }
    v.sine = { frames_checked: covered, max_abs_err: maxErr, samples_over_1e5: bad, peak, rms: Math.sqrt(ss / covered), expect_rms: 0.5 / Math.SQRT2, zero_runs_ge16: runs };
  }
  return v;
}
