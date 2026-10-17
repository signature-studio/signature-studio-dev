// COM アダプタ テストページ (tools/audio/test/page.mjs の流儀を踏襲 — ramp/sine 検証のみに簡略化)。
// com_test (wasm) を起動し、FlAudioShim を接続。結果 JSON を window.__done (Promise) へ返す。
import { FlAudioShim } from "./js/audio-shim.js";
import { ChunkVerifier, CAP_RING_FRAMES, capSpecBytes } from "./chunk_verify.mjs";

const q = new URLSearchParams(location.search);
const cfg = {
  mode: q.get("mode") ?? "ramp",
  buf: +(q.get("buf") ?? 256),
  secs: +(q.get("secs") ?? 5),
  sr: +(q.get("sr") ?? 48000),
  probe0: q.get("probe0") === "1",
};
if (cfg.probe0) FlAudioShim.prototype.probeBurst = async () => 0;   // 診断用: burst 探査を無効化 → 初期 depth は baseLatency 由来 (512 → depth 4)
const logEl = document.getElementById("log");
const shimLines = [];
const log = (s) => { logEl.textContent += s + "\n"; console.log(s); if (/\[audio-shim\]/.test(s)) shimLines.push(s); };

// main thread の heartbeat (診断): 20 ms 超の間隔を epoch ms で記録する (main thread の停止 = プロセス全体の停止の候補)
window.__hb_gaps = [];
{
  let last = performance.timeOrigin + performance.now();
  const tick = () => {
    const now = performance.timeOrigin + performance.now();
    if (now - last > 20 && window.__hb_gaps.length < 512) window.__hb_gaps.push([last, now - last]);
    last = now;
    setTimeout(tick, 5);
  };
  setTimeout(tick, 5);
}

window.__done = new Promise((resolveAll, rejectAll) => {
  let shim = null, ver = null;
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
        // キャプチャは固定容量 ring (CAP_RING_FRAMES)。全長 (secs×sr) の SAB は確保せず、照合は下のループで分割して行う
        captureFactory: (outCh, inCh) => {
          const frames = CAP_RING_FRAMES;
          const sab = new SharedArrayBuffer(capSpecBytes(frames, outCh, inCh));
          ver = new ChunkVerifier({ sab, frames, outCh, inCh }, { mode: cfg.mode, sr: cfg.sr, ring: true });
          return { sab, frames, outCh, inCh, ring: true };
        },
        onNode: async (ctx, node) => { ctxInfo = { sampleRate: ctx.sampleRate, baseLatency: ctx.baseLatency, outputLatency: ctx.outputLatency }; if (ver) ver.sr = ctx.sampleRate; void node; },
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
          if (ver) ver.step();   // リングを未照合のまま溢れさせないよう、待機ごとに畳み込む
          const r = Atomics.waitAsync(d, 0, 0, 1000);
          if (r.async) await r.value;
        }
        const code = Atomics.load(donePtr(), 0);
        let result;
        try { result = JSON.parse(M.UTF8ToString(M._com_test_result_ptr())); } catch (e) { rejectAll(new Error("bad result json")); return; }
        result.exit = code;
        result.ctx = ctxInfo;
        result.snapshot = shim.snapshot();
        // 診断計装 (判定基準は変えない): producer の write 時系列 (pw_trace: [w, fill, 起床 µs, 完了 µs] × 件)
        // と、worklet の burst_hist を結果に残す。pw_n は通算数。
        {
          const base = M._fla_ctl_ptr();
          const u32 = new Uint32Array(M.wasmMemory.buffer, base, 16904 / 4);
          const n = u32[384 / 4], N = 1024;
          const trace = [];
          const first = Math.max(0, n - N);
          for (let i = first; i < n; i++) { const k = (i % N) * 4 + 388 / 4; trace.push([u32[k], u32[k + 1], u32[k + 2], u32[k + 3]]); }
          result.pw = { pw_n: n, first_index: first, trace, burst_hist: Array.from(u32.subarray(16772 / 4, 16772 / 4 + 32)) };
        }
        // probed_burst (shim の OPEN 行) を結果に残す。判定には使わない。
        // 診断計装 (判定に使わない): producer 周期の時系列 (flasio_tl) と main thread の heartbeat 間隔 (hb_gaps: 20ms 超の間隔の
        // [開始 epoch ms, 間隔 ms])。すべて fla_now_ms と同じ epoch ms の時計 (performance.timeOrigin + now)。
        {
          const n = M._flasio_tl_count();
          const f64 = new Float64Array(M.wasmMemory.buffer, M._flasio_tl_ptr(), 2048 * 7);
          const rows = [];
          for (let i = 0; i < n; i++) rows.push(Array.from(f64.subarray(i * 7, i * 7 + 7)));
          // 段別 (JS 側 bufferSwitchTimeInfo の前後): tb = memset 直前 (in_read 後), t0 = memset 直後 (ホスト呼出し直前), cb1 = ホスト呼出し直後
          const f2 = new Float64Array(M.wasmMemory.buffer, M._flasio_tl2_ptr(), 2048 * 3);
          const seg = [];
          for (let i = 0; i < n; i++) seg.push(Array.from(f2.subarray(i * 3, i * 3 + 3)));
          result.tl = { n, cols: ["notify_ms", "fill", "underruns", "wake", "cb0", "cb1", "wr"], rows, seg_cols: ["tb", "t0", "cb1"], seg };
          // 待ち記録: out_wait の wait32 1 回ごとの [開始, 終了, rc] (rc 0=通知, 2=timeout, 1=値変化で即戻り)
          const nw = M._flasio_wt_count();
          const fw = new Float64Array(M.wasmMemory.buffer, M._flasio_wt_ptr(), 4096 * 3);
          const waits = [];
          for (let i = 0; i < nw; i++) waits.push(Array.from(fw.subarray(i * 3, i * 3 + 3)));
          result.wt = { n: nw, cols: ["t0", "t1", "rc"], waits };
        }
        result.hb_gaps = window.__hb_gaps ?? [];
        // recs = worklet の直近 64 quantum: [p, rd, wr, wl, dms (前 quantum からの Date.now 差)]
        result.ul_ms = (shim.underrunLog ?? []).map((u) => ({ ms: u.ms ?? null, p: u.p, consumed: u.consumed, recs: u.recs }));
        result.shim_open = shimLines.filter((s) => /OPEN |burst probe/.test(s));
        // 初期 depth (fla_open 直後の実効値。床 FLA_F_T_FLOOR と burst 拡張の結果)。判定には使わない。
        result.open_depth = M._flasio_open_depth();
        result.workletErrors = shim.workletErrors;
        result.cfg = cfg;
        if (ver) { result.verify = ver.finish(); result.verify.sr = ctxInfo.sampleRate; }
        resolveAll(result);
      })();
    },
  };
  const s = document.createElement("script");
  s.src = "com_test.js";
  document.body.appendChild(s);
});
