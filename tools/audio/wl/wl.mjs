// worklet 直走行版 (fla_wl) の起動ページ。URL クエリ: mode buf secs sr work_us probe neg。結果は window.__done (Promise)。
const q = new URLSearchParams(location.search);
const cfg = { mode: q.get("mode") ?? "sine", buf: +(q.get("buf") ?? 256), secs: +(q.get("secs") ?? 8), sr: +(q.get("sr") ?? 48000),
  work_us: +(q.get("work_us") ?? 0), probe: +(q.get("probe") ?? 0), neg: +(q.get("neg") ?? 0) };
const logEl = document.getElementById("log");
const log = (s) => { logEl.textContent += s + "\n"; console.log(s); };

window.__done = new Promise((resolveAll, rejectAll) => {
  const stderr = [];
  window.Module = {
    onAbort: (what) => setTimeout(() => resolveAll({ aborted: true, what: String(what), stderr, cfg }), 200),
    arguments: [`mode=${cfg.mode}`, `buf=${cfg.buf}`, `secs=${cfg.secs}`, `sr=${cfg.sr}`, `work_us=${cfg.work_us}`, `probe=${cfg.probe}`, `neg=${cfg.neg}`],
    print: (t) => log("[wasm] " + t),
    printErr: (t) => { stderr.push(String(t)); log("[wasm!] " + t); },
    onRuntimeInitialized: () => {
      const M = window.Module;
      // main thread は emscripten_exit_with_live_runtime で生存。done を futex 無しで定期確認 (SAB への Atomics.load)
      (async () => {
        const deadline = performance.now() + (cfg.secs + 40) * 1000;
        const donePtr = () => new Int32Array(M.wasmMemory.buffer, M._fla_wl_done_ptr(), 1);
        for (;;) {
          if (Atomics.load(donePtr(), 0) !== 0) break;
          if (performance.now() > deadline) { rejectAll(new Error("wl test timeout")); return; }
          await new Promise((r) => setTimeout(r, 100));
        }
        const code = Atomics.load(donePtr(), 0);
        let result;
        try { result = JSON.parse(M.UTF8ToString(M._fla_wl_result_ptr())); } catch (e) { rejectAll(new Error("bad result json")); return; }
        result.exit = code; result.ctx = M.__ctxInfo ?? {}; result.cfg = cfg; result.stderr = stderr;
        const n = Math.min(result.covered_frames, M._fla_wl_capn());
        const cap = (ptr, off) => new Float32Array(M.wasmMemory.buffer, ptr + off * 4 * M._fla_wl_capn(), M._fla_wl_capn());
        result.verify = verify(cap(M._fla_wl_cap_out(), 0), cap(M._fla_wl_cap_out(), 1), cap(M._fla_wl_cap_in(), 0), n, cfg, result.ctx.sampleRate);
        resolveAll(result);
      })();
    },
  };
  const s = document.createElement("script");
  s.src = "fla_wl.js";
  document.body.appendChild(s);
});

function verify(o0, o1, i0, covered, cfg, sr) {
  const B = cfg.buf, v = { covered_frames: covered, sr };
  if (cfg.mode === "ramp") {   // out[p] = ramp[p - B] (p >= B): 1 ブロック遅れ。先頭 B フレームは無音
    let ok = 0, bad = 0, first = -1;
    for (let p = B; p < covered; p++) { const e = p - B + 1; if (o0[p] === e && o1[p] === -e) ok++; else { bad++; if (first < 0) first = p; } }
    let head = 0; for (let p = 0; p < B; p++) if (o0[p] !== 0) head++;
    v.ramp = { frames_checked: covered - B, bit_exact: ok, mismatches: bad, first_mismatch_frame: first, head_nonzero: head };
  } else if (cfg.mode === "sine") {
    let maxErr = 0, runs = 0, run = 0;
    for (let p = B; p < covered; p++) {
      const d = Math.max(Math.abs(o0[p] - 0.5 * Math.sin(2 * Math.PI * 440 * (p - B) / sr)), Math.abs(o1[p] - 0.5 * Math.sin(2 * Math.PI * 660 * (p - B) / sr)));
      if (d > maxErr) maxErr = d;
      if (o0[p] === 0) { run++; if (run === 16) runs++; } else run = 0;
    }
    v.sine = { frames_checked: covered - B, max_abs_err: maxErr, zero_runs_ge16: runs };
  } else {   // loop: 入力→出力の相互相関ピーク (tools/audio/test/page.mjs と同じ手順・1 s 窓)
    const W = Math.min(sr, Math.max(0, covered - sr)), base = Math.min(Math.floor(sr / 2), Math.max(0, covered - W - 9000));
    let e_in = 0; for (let k = 0; k < W; k++) e_in += i0[base + k] * i0[base + k];
    let best = -1, bestLag = -1;
    for (let lag = 0; lag <= 8192; lag++) {
      let s = 0, eo = 0;
      for (let k = 0; k < W; k++) { const o = o0[base + k + lag]; s += i0[base + k] * o; eo += o * o; }
      const nc = e_in > 0 && eo > 0 ? s / Math.sqrt(e_in * eo) : 0;
      if (nc > best) { best = nc; bestLag = lag; }
    }
    v.loop = { window: W, base, best_norm_corr: best, lag_frames: bestLag, lag_ms: bestLag * 1000 / sr, input_rms: Math.sqrt(e_in / W) };
  }
  return v;
}
