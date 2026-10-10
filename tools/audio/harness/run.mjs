// シナリオ行列ランナー: 1 つの headless Chrome で全シナリオを順に実行し、結果 JSON と判定を出力する。
// 使い方: node harness/run.mjs [--quick] [--only name,name] [--out results/results.json]
import { withChrome } from "./chrome.mjs";
import path from "node:path"; import fs from "node:fs"; import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const quick = args.includes("--quick");
const only = args.includes("--only") ? args[args.indexOf("--only") + 1].split(",") : null;
const outFile = args.includes("--out") ? args[args.indexOf("--out") + 1] : path.join(here, "../results/results.json");
const S = (full, q) => (quick ? q : full);

// expect: 判定関数 (r) => [ok:boolean, msg]
const underrunFree = (r) => [r.stats.underruns === 0 && r.stats.silence_frames === 0, `underruns=${r.stats.underruns} silence=${r.stats.silence_frames}`];
const rampExact = (r) => [r.verify?.ramp && r.verify.ramp.mismatches === 0 && r.verify.ramp.frames_checked > 0, `ramp mismatches=${r.verify?.ramp?.mismatches}/${r.verify?.ramp?.frames_checked}`];
const sineOk = (r) => [r.verify?.sine && r.verify.sine.max_abs_err < 1e-5 && r.verify.sine.zero_runs_ge16 === 0, `sine maxErr=${r.verify?.sine?.max_abs_err?.toExponential(2)} rms=${r.verify?.sine?.rms?.toFixed(4)} zeroRuns=${r.verify?.sine?.zero_runs_ge16}`];
const all = (...fs) => (r) => { const rs = fs.map((f) => f(r)); return [rs.every((x) => x[0]), rs.map((x) => x[1]).join("; ")]; };

const scenarios = [];
for (const buf of [128, 256, 512, 1024])
  scenarios.push({ name: `asio_ramp_b${buf}_d2`, q: `api=asio&mode=ramp&buf=${buf}&depth=2&secs=${S(20, 4)}`, expect: all(underrunFree, rampExact) });
scenarios.push({ name: "asio_sine_b256_d2", q: `api=asio&mode=sine&buf=256&depth=2&secs=${S(15, 4)}`, expect: all(underrunFree, sineOk) });
scenarios.push({ name: "asio_sine_b512_d4_44k", q: `api=asio&mode=sine&buf=512&depth=4&sr=44100&secs=${S(10, 4)}`, expect: all(underrunFree, sineOk) });
scenarios.push({ name: "asio_sine_b256_96k", q: `api=asio&mode=sine&buf=256&depth=2&sr=96000&secs=${S(10, 4)}`, expect: all(underrunFree, sineOk) });
// 過負荷: 6 本の busy スレッド + main thread 30ms/100ms ブロック + コールバック毎 1.5ms 相当の演算。共有ホスト (load avg ~12/16コア) 上。
// 合格条件 = 「劣化しても連続性が保たれる」: underruns<=5 かつ復帰後 ramp[p-S] 完全一致 (underrun 件数自体は実測値として記録)
scenarios.push({ name: "asio_ramp_b256_load", q: `api=asio&mode=ramp&buf=256&depth=2&stress=6&jank=1&work_us=1500&secs=${S(20, 5)}`,
  expect: (r) => { const t = r.verify.ramp.tail_shift_exact; return [r.stats.underruns <= 5 && t.exact === t.checked && t.checked > 0 && r.workletErrors.length === 0,
    `過負荷: underruns=${r.stats.underruns} silence=${r.stats.silence_frames}f, 復帰後 ramp[p-S] 一致 ${t.exact}/${t.checked}`]; } });
scenarios.push({ name: "asio_sine_b256_timeinfo", q: `api=asio&mode=sine&buf=256&depth=2&timeinfo=1&secs=${S(10, 4)}`,
  expect: (r) => { const [a, m1] = all(underrunFree, sineOk)(r); return [a && r.timeinfo.calls > 0 && r.timeinfo.bad === 0 && r.timeinfo.calls >= r.stats.timeinfo_cb && r.timeinfo.calls - r.stats.timeinfo_cb <= 16, `${m1}; bufferSwitchTimeInfo calls=${r.timeinfo.calls} bad=${r.timeinfo.bad}`]; } });
scenarios.push({ name: "asio_sine_b256_setsr_48k_to_44k", q: `api=asio&mode=sine&buf=256&depth=2&sr=48000&sr_after=44100&secs=${S(8, 4)}`,
  expect: (r) => { const [a, m1] = all(underrunFree, sineOk)(r); return [a && r.ctx.sampleRate === 44100 && r.rate_changes === 1, `${m1}; ctx.sampleRate=${r.ctx.sampleRate} sampleRateDidChange=${r.rate_changes}`]; } });
scenarios.push({ name: "asio_ramp_b256_hiccup", q: `api=asio&mode=ramp&buf=256&depth=2&hiccup_ms=60&hiccup_every=200&secs=${S(15, 6)}`,
  expect: (r) => { const t = r.verify.ramp.tail_shift_exact; return [r.stats.underruns > 0 && r.stats.silence_frames > 0 && t.exact === t.checked && t.checked > 0 && r.workletErrors.length === 0,
    `強制 60ms hiccup: underruns=${r.stats.underruns} silence=${r.stats.silence_frames}f → 復帰後 ramp[p-S] 一致 ${t.exact}/${t.checked}`]; } });
scenarios.push({ name: "asio_ramp_b256_suspend", q: `api=asio&mode=ramp&buf=256&depth=2&suspend=1&secs=${S(10, 5)}`,
  expect: (r) => [r.resets_seen >= 1 && r.workletErrors.length === 0, `kAsioResetRequest 受信=${r.resets_seen}, underruns=${r.stats.underruns}`] });
for (const buf of [128, 256, 512])
  scenarios.push({ name: `asio_loop_noise_b${buf}`, q: `api=asio&mode=loop&input=noise&buf=${buf}&depth=2&secs=${S(8, 5)}`,
    expect: (r) => [r.verify?.loop && r.verify.loop.best_norm_corr > 0.99 && r.stats.in_overruns === 0 && r.stats.underruns === 0, `lag=${r.verify?.loop?.lag_frames}f (${r.verify?.loop?.lag_ms?.toFixed(2)}ms) corr=${r.verify?.loop?.best_norm_corr?.toFixed(4)} in_overruns=${r.stats.in_overruns} in_underflows=${r.stats.in_underflows}`] });
scenarios.push({ name: "asio_loop_gum_fake_b256", q: `api=asio&mode=loop&input=gum&buf=256&depth=2&secs=${S(8, 5)}`,
  expect: (r) => [r.verify?.loop && r.verify.loop.input_rms > 1e-4 && r.workletErrors.length === 0, `gum input_rms=${r.verify?.loop?.input_rms?.toExponential(2)} corr=${r.verify?.loop?.best_norm_corr?.toFixed(3)} lag=${r.verify?.loop?.lag_frames}f tracks=${JSON.stringify(r.ctx?.gumTracks?.map((t) => t.label))}`] });
scenarios.push({ name: "wasapi_ramp_b512_d2", q: `api=wasapi&mode=ramp&buf=512&depth=2&secs=${S(15, 4)}`, expect: all(underrunFree, rampExact) });
scenarios.push({ name: "wasapi_sine_b256_d3", q: `api=wasapi&mode=sine&buf=256&depth=3&secs=${S(10, 4)}`, expect: all(underrunFree, sineOk) });
if (!quick) scenarios.push({ name: "asio_ramp_b256_soak120", q: "api=asio&mode=ramp&buf=256&depth=2&secs=120", expect: all(underrunFree, rampExact) });

// fail-fast / 戻り値検証 (AudioContext を開かない)
scenarios.push({ name: "failfast_asio_uninit", q: "api=ff_uninit&secs=1", expect: (r) => [r.aborted && r.stderr.some((l) => l.includes("FAIL-FAST: flasio_get_channels: driver not initialised")), `abort stderr=${JSON.stringify(r.stderr?.filter((l) => l.includes("FAIL-FAST")))}`] });
scenarios.push({ name: "failfast_wasapi_exclusive", q: "api=ff_excl&secs=1", expect: (r) => [r.aborted && r.stderr.some((l) => l.includes("FAIL-FAST: flwasapi_initialize")), `abort stderr=${JSON.stringify(r.stderr?.filter((l) => l.includes("FAIL-FAST")))}`] });
scenarios.push({ name: "asio_apicheck", q: "api=apicheck&secs=1",
  expect: (r) => { const c = r.codes ?? {}; const want = { createBuffers_100: -997, createBuffers_8192: -997, createBuffers_badch: -997, createBuffers_nullinfo: -998, setSampleRate_12345: -995,
    canSampleRate_44100: 0, getSamplePosition_stopped: -996, outputReady: -1000, future: -998, getChannelInfo_ch7: -998, setClockSource_1: -998, getClockSources: 0, clock_n: 1, start_nobuf: -997, getSampleRate: 0, rate: 48000 };
    const bad = Object.keys(want).filter((k) => c[k] !== want[k]); return [bad.length === 0, bad.length ? "mismatch: " + bad.map((k) => `${k}=${c[k]}(want ${want[k]})`).join(", ") : `ASIO エラーコード 16 項目一致`]; } });

const sel = scenarios.filter((s) => !only || only.includes(s.name));
const results = [];
let failed = 0;
await withChrome({ root: path.join(here, "../build/web"), page: "index.html?" + sel[0].q, log: () => {} }, async (cdp) => {
  let first = true;
  for (const sc of sel) {
    if (!first) await cdp.navigate("index.html?" + sc.q);
    first = false;
    let r, err = null;
    try { r = await cdp.eval("window.__done"); } catch (e) { err = String(e); }
    let ok = false, msg = err ?? "";
    if (r) [ok, msg] = sc.expect(r);
    if (!ok) failed++;
    results.push({ name: sc.name, query: sc.q, ok, msg, result: r ?? null, error: err });
    const st = r?.stats ?? {};
    if (r && (r.aborted || r.codes)) { console.log(`${ok ? "PASS" : "FAIL"} ${sc.name.padEnd(28)} ${msg}`); continue; }
    console.log(`${ok ? "PASS" : "FAIL"} ${sc.name.padEnd(28)} ${msg}` +
      (r ? `\n       cb=${st.cb_count ?? st.fills} late=${st.cb_late ?? "-"} cb_max=${st.cb_max_us ?? st.fill_max_us}us burst=${st.burst_obs ?? "-"} T=${st.T ?? "-"} (${st.T ? (st.T * 1000 / r.sr).toFixed(1) : "-"}ms) lat_changes=${st.latency_changes ?? "-"} wake_hist=${JSON.stringify(st.wake_hist)} ` +
        `dev_fill[min/avg/max]=${r.verify?.device_fill?.min}/${r.verify?.device_fill?.avg?.toFixed(0)}/${r.verify?.device_fill?.max} ` +
        `jumps=${r.snapshot?.clock_jumps}/${r.snapshot?.clock_jump_frames}f lat(in/out)=${r.reported?.lat_in ?? "-"}/${r.reported?.lat_out ?? "-"} clock=${r.clock?.rate_hz?.toFixed(1) ?? "-"}Hz` : ""));
  }
});
fs.mkdirSync(path.dirname(outFile), { recursive: true });
let merged = results;
if (only && fs.existsSync(outFile)) {   // 部分再実行: 既存結果へ名前単位でマージ
  const old = JSON.parse(fs.readFileSync(outFile, "utf8")).results;
  const names = new Set(results.map((x) => x.name));
  merged = [...old.filter((x) => !names.has(x.name)), ...results];
}
for (const x of results) x.ran_at = new Date().toISOString();
fs.writeFileSync(outFile, JSON.stringify({ date: new Date().toISOString(), quick, chrome: "headless google-chrome 154", note: "ran_at は部分再実行時のシナリオ単位時刻", results: merged }, null, 1));
console.log(`\n${results.length - failed}/${results.length} PASS -> ${outFile}${only ? " (部分実行: 既存結果へマージ)" : ""}`);
process.exit(failed ? 1 : 0);
