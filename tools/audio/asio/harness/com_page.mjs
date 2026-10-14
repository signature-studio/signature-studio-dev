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
const log = (s) => { logEl.textContent += s + "\n"; console.log(s); };

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
