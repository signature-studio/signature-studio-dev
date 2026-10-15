// AU-2 (#187) Firefox 行列の 1 rep: Firefox (WebDriver BiDi) で {48k, 96k (B=256), 96k (B=512)} の sine 経路を測る。au2_firefox_matrix.sh と Windows / macOS の workflow から呼ぶ。
// 使い方: node harness/au2.mjs --rep <n> [--secs 10] [--out results/au2/firefox_r<n>.json]
// 比較対象の名前は run.mjs と同じ (48k = asio_sine_b256_d2, 96k = asio_sine_b256_96k, 96k B=512 = asio_sine_b512_96k)。
// 既定出力の判定は OS 別: Linux = PulseAudio の ci_null (sink-input を再生中に採取)、Windows = 既定の再生デバイスが CABLE Input (VB-CABLE)、macOS = 既定出力が BlackHole 2ch。
import { withFirefox } from "./bidi.mjs";
import fs from "node:fs"; import os from "node:os"; import path from "node:path";
import { fileURLToPath } from "node:url"; import { execFileSync } from "node:child_process";
const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const argOf = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const rep = +argOf("--rep", "1");
const secs = +argOf("--secs", "10");
// --extra: 全シナリオの query に追加する (ネガティブコントロール用。例: hiccup_ms=60&hiccup_every=200 で underrun を強制し FAIL することを確認)
const extra = argOf("--extra", "");
const outFile = argOf("--out", path.join(here, "../results/au2", `firefox_r${rep}.json`));
const withExtra = (q) => (extra ? `${q}&${extra}` : q);
const SCEN = [
  { name: "asio_sine_b256_d2", sr: 48000, q: withExtra(`api=asio&mode=sine&buf=256&depth=2&secs=${secs}`) },
  { name: "asio_sine_b256_96k", sr: 96000, q: withExtra(`api=asio&mode=sine&buf=256&depth=2&sr=96000&secs=${secs}`) },
  { name: "asio_sine_b512_96k", sr: 96000, q: withExtra(`api=asio&mode=sine&buf=512&depth=2&sr=96000&secs=${secs}`) },
];
// 受入 4: AudioWorklet・SharedArrayBuffer・Atomics.wait の制約。worklet 内の Atomics.wait が可能か、notify が使えるかを実測する
const PROBE = `(async () => {
  const out = { ua: navigator.userAgent, crossOriginIsolated, sab: typeof SharedArrayBuffer };
  try { out.wait_main = Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 0); } catch (e) { out.wait_main = "throw " + e.name; }
  const src = 'class P extends AudioWorkletProcessor { constructor() { super(); const r = {}; try { const t = Date.now(); r.wait = Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 20); r.wait_ms = Date.now() - t; } catch (e) { r.wait = "throw " + e.name; } r.notify = typeof Atomics.notify; this.port.postMessage(r); } process() { return false; } } registerProcessor("probe", P);';
  const ctx = new AudioContext({ sampleRate: 48000 });
  await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([src], { type: "text/javascript" })));
  const node = new AudioWorkletNode(ctx, "probe");
  out.worklet = await new Promise((ok) => { node.port.onmessage = (e) => ok(e.data); setTimeout(() => ok("timeout"), 5000); });
  out.worklet_ctx_state = ctx.state;
  await ctx.close();
  return out;
})()`;
// 既定出力の判定 (OS 別)。Linux は PulseAudio の ci_null (workflow が無くても harness/run.mjs と同じ前提)。Windows・macOS は workflow が仮想デバイスを既定の出力にする
const OS = process.platform;
const EXPECTED = { linux: "ci_null", win32: "CABLE Input", darwin: "BlackHole 2ch" }[OS] ?? null;
const hasExpected = (s) => !!EXPECTED && !!s?.includes(EXPECTED);
const cmd = (c, a) => { try { return execFileSync(c, a, { encoding: "utf8", timeout: 15000 }).trim(); } catch (e) { return "ERR " + e.message; } };
const pactl = (...a) => cmd("pactl", a);
// Windows: AudioDeviceCmdlets の Get-AudioDevice (workflow が導入)。macOS: switchaudio-osx の SwitchAudioSource (workflow が導入)
const defaultOutput = () => (OS === "win32" ? cmd("powershell", ["-NoProfile", "-Command", "(Get-AudioDevice -Playback).Name"]) : OS === "darwin" ? cmd("SwitchAudioSource", ["-c", "-t", "output"]) : null);
const ciNull = () => pactl("list", "short", "sinks").split("\n").map((l) => l.split("\t")).find((c) => c[1] === "ci_null") ?? null;
// 再生の前後で既定出力の名前を採る (Windows・macOS は per-stream の sink-input に当たる情報が OS 側に無い)。
// Linux は再生中に 300 ms ごとに sink-input を採取し、それが ci_null (既定 sink) の index に繋がったかを記録する
// pactl list short sink-inputs の列 (PulseAudio 16.1 実測): index / sink / client / driver / spec (state 列は無い)
function watchSink(sinkIdx) {
  if (OS !== "linux") {
    const before = defaultOutput();
    return { stop: () => {}, summary: () => { const after = defaultOutput(); return { seen: true, on_expected: hasExpected(before) && hasExpected(after), expected: EXPECTED, default_before: before, default_after: after, specs: [] }; } };
  }
  const seen = new Map();
  const iv = setInterval(() => {
    for (const l of pactl("list", "short", "sink-inputs").split("\n").filter(Boolean)) {
      const c = l.split("\t");
      seen.set(l, { sink: c[1], spec: c[4] });
    }
  }, 300);
  return { stop: () => clearInterval(iv), summary: () => { const rows = [...seen.values()]; return { seen: rows.length > 0, on_expected: rows.some((r) => r.sink === sinkIdx), expected: EXPECTED, specs: [...new Set(rows.map((r) => r.spec))] }; } };
}
const underrunFree = (r) => r.stats.underruns === 0 && r.stats.silence_frames === 0;
const sineOk = (r) => r.verify?.sine && r.verify.sine.max_abs_err < 1e-5 && r.verify.sine.zero_runs_ge16 === 0;

const loadStart = os.loadavg(), tStart = Date.now();
const sinkBefore = OS === "linux" ? ciNull() : null;
const results = [];
let failed = 0, probe = null;
// 初回のシナリオは withFirefox の page で開く (navigate は 1 回だけ。run.mjs の first と同じ扱い)
await withFirefox({ root: path.join(here, "../build/web"), page: "index.html?" + SCEN[0].q }, async (ff) => {
  let first = true;
  for (const sc of SCEN) {
    const watch = watchSink(sinkBefore?.[0]);
    let r = null, err = null;
    try { if (!first) await ff.navigate("index.html?" + sc.q); r = await ff.eval("window.__done"); } catch (e) { err = String(e); }
    first = false;
    watch.stop();
    const conn = watch.summary();
    let ok = false, msg = err ?? "";
    if (r) {
      const rateOk = r.ctx?.sampleRate === sc.sr;
      ok = !r.aborted && underrunFree(r) && !!sineOk(r) && rateOk && (r.workletErrors ?? []).length === 0 && conn.on_expected;
      msg = `underruns=${r.stats.underruns} silence=${r.stats.silence_frames}f sine maxErr=${r.verify?.sine?.max_abs_err?.toExponential(2)} zeroRuns=${r.verify?.sine?.zero_runs_ge16} ctx.sampleRate=${r.ctx?.sampleRate}(want ${sc.sr}) on expected sink=${conn.on_expected}`;
    }
    if (!ok) failed++;
    const s = r?.stats ?? {};
    results.push({ name: sc.name, sr: sc.sr, query: sc.q, ok, msg, error: err, sink_route: conn,
      ctx: r?.ctx ?? null, burst: s.burst_obs ?? null, T: s.T ?? null, clock_hz: r?.clock?.rate_hz ?? null, underruns: s.underruns ?? null,
      silence_frames: s.silence_frames ?? null, cb_count: s.cb_count ?? null, result: r });
    console.log(`${ok ? "PASS" : "FAIL"} ${sc.name.padEnd(24)} ${msg}${err ? " ERR " + err : ""}`);
    console.log(`       burst=${s.burst_obs ?? "-"} T=${s.T ?? "-"} clock=${r?.clock?.rate_hz?.toFixed(1) ?? "-"}Hz on expected sink=${conn.on_expected} specs=${JSON.stringify(conn.specs)}`);
  }
  probe = await ff.eval(PROBE);
});
const out = { browser: "firefox", os: OS, expected_sink: EXPECTED, rep, secs, extra, date: new Date().toISOString(), load_start: loadStart, load_end: os.loadavg(), nproc: os.cpus().length,
  wall_s: (Date.now() - tStart) / 1000, pulse: OS === "linux" ? { default_sink: pactl("get-default-sink").trim(), ci_null_before: sinkBefore } : null, probe, results, failed, rc: failed ? 1 : 0 };
fs.mkdirSync(path.dirname(outFile), { recursive: true });
fs.writeFileSync(outFile, JSON.stringify(out, null, 1));
console.log(`probe: ${JSON.stringify(probe)}`);
console.log(`${SCEN.length - failed}/${SCEN.length} PASS (rep ${rep}, wall ${out.wall_s.toFixed(1)}s, load ${loadStart.map((v) => v.toFixed(2))} -> ${out.load_end.map((v) => v.toFixed(2))}) -> ${outFile}`);
process.exit(failed ? 1 : 0);
