// AU-8 (#194): ring 方式 (fla_test = ASIO 風 producer スレッド + SAB ring) vs worklet 直走行 (fla_wl) の遅延比較ランナー。
// 使い方: node tools/audio/wl/run.mjs [--reps 3] [--secs 6] [--out tools/audio/wl/results/results.json]
// 終了コード: 全 gate PASS かつ 全ネガコン (壊した入力で検査器が FAIL を出せること) が成立したときだけ 0。外れれば 1 (結果 JSON は常に書く)。
import { withChrome } from "../harness/chrome.mjs";
import path from "node:path"; import fs from "node:fs"; import os from "node:os"; import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const REPS = +opt("--reps", 3), SECS = +opt("--secs", 6);
const outFile = opt("--out", path.join(here, "results/results.json"));
const BUFS = [128, 256, 512];

const gates = [];   // { name, ok, msg, expectFail?, kind }
const raw = [];
// ok = この項目の合格。negctl 項目は「壊した入力で検査器が FAIL を出せた」ときに ok=true (検出できなければ ok=false = 検査器が空振り)
const gate = (name, ok, msg, extra = {}) => { gates.push({ name, ok: !!ok, msg, ...extra }); console.log(`${ok ? "PASS" : "FAIL"} ${name}${extra.negctl ? " [negctl]" : ""}  ${msg}`); };
const med = (a) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };

const wlQ = (o) => "wl.html?" + new URLSearchParams(o).toString();
const ringQ = (o) => "index.html?" + new URLSearchParams(o).toString();

// ---- gate 関数 (negctl は同じ関数を「壊した入力」に適用して FAIL することを確認する) ----
const wlRampOk = (r) => r.verify?.ramp && r.verify.ramp.mismatches === 0 && r.verify.ramp.frames_checked > 100000 && r.verify.ramp.head_nonzero === 0 && r.clock_jumps === 0;
const wlLoopLagIsB = (r, B) => r.verify?.loop && r.verify.loop.best_norm_corr > 0.99 && r.verify.loop.lag_frames === B;

const t0 = Date.now(); const load0 = os.loadavg()[0];
await withChrome({ root: path.join(here, "../build/web"), page: wlQ({ mode: "ramp", buf: 256, secs: 1 }), log: () => {} }, async (cdp) => {
  const run = async (page) => { await cdp.navigate(page); try { return await cdp.eval("window.__done"); } catch (e) { return { error: String(e) }; } };

  // (1) worklet 直走行: ramp bit-exact (出力は 1 ブロック遅れ)
  for (const B of BUFS) {
    const r = await run(wlQ({ mode: "ramp", buf: B, secs: SECS })); raw.push({ name: `wl_ramp_b${B}`, r });
    gate(`wl_ramp_b${B}`, wlRampOk(r), `ramp ${r.verify?.ramp?.bit_exact}/${r.verify?.ramp?.frames_checked} bit-exact, jumps=${r.clock_jumps}, renders=${r.renders}, gap_max=${r.gap_max_ms}ms`);
  }
  // (2) 遅延: 入力→出力 lag。worklet 直走行 vs ring。各 REPS 回
  const lag = { wl: {}, ring: {}, ringT: {}, ringOut: {} };
  for (const B of BUFS) {
    lag.wl[B] = []; lag.ring[B] = []; lag.ringT[B] = [];
    for (let k = 0; k < REPS; k++) {
      const w = await run(wlQ({ mode: "loop", buf: B, secs: SECS })); raw.push({ name: `wl_loop_b${B}_${k}`, r: w });
      gate(`wl_loop_b${B}#${k}`, wlLoopLagIsB(w, B), `lag=${w.verify?.loop?.lag_frames}f (${w.verify?.loop?.lag_ms?.toFixed(2)}ms) corr=${w.verify?.loop?.best_norm_corr?.toFixed(4)} (want lag=${B}f)`);
      lag.wl[B].push(w.verify?.loop?.lag_frames ?? NaN);
      const g = await run(ringQ({ api: "asio", mode: "loop", input: "noise", buf: B, depth: 2, secs: SECS })); raw.push({ name: `ring_loop_b${B}_${k}`, r: g });
      const okg = g.verify?.loop && g.verify.loop.best_norm_corr > 0.99 && g.stats?.underruns === 0 && g.stats?.in_overruns === 0;
      gate(`ring_loop_b${B}#${k}`, okg, `lag=${g.verify?.loop?.lag_frames}f (${g.verify?.loop?.lag_ms?.toFixed(2)}ms) T=${g.stats?.T}f burst_obs=${g.stats?.burst_obs} corr=${g.verify?.loop?.best_norm_corr?.toFixed(4)} underruns=${g.stats?.underruns} in_overruns=${g.stats?.in_overruns}`);
      lag.ring[B].push(g.verify?.loop?.lag_frames ?? NaN); lag.ringT[B].push(g.stats?.T ?? NaN);
    }
  }
  // (3) 比較 gate: 各 B で worklet 直走行の lag が ring の全 run の lag より小さい (最大の wl < 最小の ring)
  const summary = {};
  for (const B of BUFS) {
    const wmax = Math.max(...lag.wl[B]), rmin = Math.min(...lag.ring[B]);
    summary[B] = { wl_lag_frames: lag.wl[B], ring_lag_frames: lag.ring[B], ring_T_frames: lag.ringT[B],
      wl_median_ms: med(lag.wl[B]) * 1000 / 48000, ring_median_ms: med(lag.ring[B]) * 1000 / 48000, saved_median_ms: (med(lag.ring[B]) - med(lag.wl[B])) * 1000 / 48000 };
    gate(`compare_b${B}`, wmax < rmin, `worklet 直走行 lag max=${wmax}f < ring lag min=${rmin}f  (中央値 ${summary[B].wl_median_ms.toFixed(2)}ms vs ${summary[B].ring_median_ms.toFixed(2)}ms, 差 ${summary[B].saved_median_ms.toFixed(2)}ms)`);
  }
  // (4) 負荷: 模擬 render 負荷 (ブロック予算に対する割合)。B=256@48k の予算 = 5333us
  const budget = 256 * 1e6 / 48000;
  for (const frac of [0.75, 1.5]) {
    const wu = Math.round(budget * frac);
    const w = await run(wlQ({ mode: "ramp", buf: 256, secs: SECS, work_us: wu })); raw.push({ name: `wl_load_${frac}`, r: w });
    const g = await run(ringQ({ api: "asio", mode: "ramp", buf: 256, depth: 2, secs: SECS, work_us: wu })); raw.push({ name: `ring_load_${frac}`, r: g });
    const wlHealthy = w.verify?.ramp?.mismatches === 0 && w.clock_jumps === 0 && w.rt_ratio > 0.99;
    const ringHealthy = g.stats?.underruns === 0;
    if (frac < 1) {
      gate(`load_${frac}_wl`, wlHealthy, `work=${wu}us/予算${budget.toFixed(0)}us: ramp 不一致 ${w.verify?.ramp?.mismatches}, jumps=${w.clock_jumps}, rt_ratio=${w.rt_ratio}, 較正 ${w.iters_per_us} iter/us`);
      gate(`load_${frac}_ring`, ringHealthy, `work=${wu}us: underruns=${g.stats?.underruns} T=${g.stats?.T}f cb_max=${g.stats?.cb_max_us}us`);
    } else {
      // 予算超過: worklet 直走行は「壊れる」ことが期待 (= 検出能力のネガコン)。ring も平均負荷が予算超なので壊れる (underrun>0) 期待
      gate(`overload_${frac}_wl_detects`, !wlHealthy, `work=${wu}us>予算: 健全性 gate が FAIL を検出 (ramp 不一致 ${w.verify?.ramp?.mismatches}, jumps=${w.clock_jumps}, rt_ratio=${w.rt_ratio})`, { negctl: true });
      gate(`overload_${frac}_ring_detects`, !ringHealthy, `work=${wu}us>予算: underruns=${g.stats?.underruns} (>0 を期待)`, { negctl: true });
    }
  }
  // (5) worklet 内のブロッキング: memory.atomic.wait32 は到達後に戻らず process() が止まる (quanta=10 で停止)
  const p = await run(wlQ({ mode: "sine", buf: 256, secs: 3, probe: 2 })); raw.push({ name: "wl_probe_wait32", r: p });
  gate("wl_probe_atomic_wait32_traps", p.probe?.atomic_wait32 === 100 && p.quanta === 10, `到達マーカ=${p.probe?.atomic_wait32} (100=到達後に戻らず) quanta=${p.quanta} (10 で停止 = process() が死んだ) 3s 後`);

  // (6) ネガティブコントロール (同じ gate を壊した入力に適用して FAIL を確認)
  const nr = await run(wlQ({ mode: "loop", buf: 256, secs: SECS, neg: 1 })); raw.push({ name: "neg_wl_loop_no_input", r: nr });
  gate("neg_loop_gate_no_input", !wlLoopLagIsB(nr, 256), `入力を接続しない loop: corr=${nr.verify?.loop?.best_norm_corr} input_rms=${nr.verify?.loop?.input_rms} → lag gate が FAIL`, { negctl: true });
  const anyRing = raw.find((x) => x.name.startsWith("ring_loop_b256"))?.r;
  gate("neg_wl_gate_on_ring_result", !wlLoopLagIsB({ verify: anyRing?.verify }, 256), `ring の lag=${anyRing?.verify?.loop?.lag_frames}f を wl 用 gate (lag==256) に通す → FAIL`, { negctl: true });
  const w0 = raw.find((x) => x.name === "wl_ramp_b256").r;
  const broken = structuredClone(w0); broken.verify.ramp.mismatches = 1;
  gate("neg_ramp_gate_one_mismatch", !wlRampOk(broken), "ramp を 1 件壊した結果は wlRampOk が FAIL", { negctl: true });
  raw.push({ name: "summary", r: summary });
});

const failed = gates.filter((g) => !g.ok).length;
const seconds = (Date.now() - t0) / 1000;
fs.mkdirSync(path.dirname(outFile), { recursive: true });
fs.writeFileSync(outFile, JSON.stringify({ date: new Date().toISOString(), reps: REPS, secs: SECS, elapsed_s: seconds, loadavg_start: load0, loadavg_end: os.loadavg()[0],
  chrome: "headless google-chrome", gates, failed, raw }, null, 1));
console.log(`\n${gates.length - failed}/${gates.length} 合格 (うち negctl ${gates.filter((g) => g.negctl).length} 件), 所要 ${seconds.toFixed(1)} s, load avg 開始 ${load0.toFixed(2)} / 終了 ${os.loadavg()[0].toFixed(2)} -> ${outFile}`);
process.exit(failed ? 1 : 0);
