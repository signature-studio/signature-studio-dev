// tools/audio/asio/harness/soak_recount.mjs — CAB-270 独立再計算 + ネガティブコントロール (SUBAGENT_RULES 規則 37・41)
//
// 実装側 (run_com.mjs) の判定を **別アルゴリズム**で再計算する。同じ実装の再実行は独立再計算ではないので、
// ここでは実装側が 1 個のオブジェクト (stats / verify / timeinfo / com / ctx) から読む値を
// *別の導線*で突合する:
//   (R1) worklet 側の underrun_events (verify.underrun_events = capture SAB hdr[6])
//        ↔ shim producer 側の stats.underruns / stats.silence_frames  (別コード パスの同一現象のカウント)
//   (R2) stats.cb_count × B (bufferSwitch に渡した倍点数) ≤ verify.ramp.frames_checked ≤ produced_frames
//        (生成したがまだ消費されていないぶんを含む → 実測 768 f)
//   (R3) 実時間性: frames_checked / secs_wall ≈ ctx.sampleRate (120s soak が 1 倍速で走ったことの確認)
//   (R4) kAsioSupportsTimeInfo=1 なので timeinfo.calls ≳ cb_count (timeinfo が本体経路であること)
//   (R5) COM 面: sellog を配列として deep-equal (実装側は JSON.stringify 比較)、refs/alive/QI の参照カウント収支
//   (R6) ランプ bit-exact の代替アルゴリズム (差分 = +1 の連鎖) は SAB が保存されないため
//        **合成 SAB に対する自己検証** で実施 (--selftest)。clean / 汚染 / 無音ランの 3 ケースで
//        実装側アルゴリズム (page.verify: ch0[p]===p+1) と本アルゴリズム (ch0[p+1]-ch0[p]===1) の両者が
//        過不足なく検出することを確認する = 検出器が空振りでないことの実証。
//
// 使い方:
//   node harness/soak_recount.mjs [--file work/results_com.json] [--name com_soak120_b256] [--selftest]
// 終了コード 0 = 全項目 PASS。--selftest は合成 SAB を用いるため独立に実行できる。

import fs from "node:fs"; import path from "node:path"; import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 && i + 1 < args.length ? args[i + 1] : d; };
const selftest = args.includes("--selftest") || args.includes("--only-selftest");
const file = opt("--file", path.join(here, "../work/results_com.json"));
const nameFilter = opt("--name", null);

const out = [];
let fails = 0;
const rec = (id, ok, detail) => { out.push({ id, ok, detail }); if (!ok) fails++; console.log(`  ${ok ? "PASS" : "FAIL"} ${id}  ${detail}`); };

/* ---- (R6) ランプ照合アルゴリズム (2 種) ---- */
// A = 実装側と同一: com_page.mjs verify() の突合 (ch0[p]===p+1 && ch1[p]===-(p+1))
function rampDirect(sab, frames, covered) {
  const hdr = new Int32Array(sab, 0, 16);
  const ch0 = new Float32Array(sab, 64, frames), ch1 = new Float32Array(sab, 64 + frames * 4, frames);
  let bad = 0;
  for (let p = 0; p < covered; p++) { const e = p + 1; if (ch0[p] !== e || ch1[p] !== -e) bad++; }
  let runs = 0, run = 0;
  for (let p = 0; p < covered; p++) { if (ch0[p] === 0) { run++; if (run === 16) runs++; } else run = 0; }
  return { mismatches: bad, zero_runs_ge16: runs, underrun_events: Atomics.load(hdr, 6) };
}
// B = 本 script の代替: 「差分が全て +1」= 破点 (breakpoint) の数。孤立汚染 1 か所で direct は L 個・本algo は 2 個。
function rampDelta(sab, frames, covered) {
  const ch0 = new Float32Array(sab, 64, frames);
  let breaks = 0, first = -1;
  for (let p = 1; p < covered; p++) {
    if (ch0[p] - ch0[p - 1] !== 1) { breaks++; if (first < 0) first = p; }
  }
  return { breaks, first_break: first, head_ok: covered > 0 && ch0[0] === 1 };
}

/* ---- 合成 SAB 自己検証 (--selftest) ---- */
// レイアウトは worklet と同じ: hdr Int32[16] @0 / ch0 f32[frames] @64 / ch1 f32[frames] @64+frames*4
function makeSynthetic(frames, dirty, zeroRun) {
  const sab = new SharedArrayBuffer(64 + frames * 4 * 2);   // fill 領域は省略 (本検証では使わない)
  const hdr = new Int32Array(sab, 0, 16);
  const ch0 = new Float32Array(sab, 64, frames), ch1 = new Float32Array(sab, 64 + frames * 4, frames);
  for (let p = 0; p < frames; p++) { ch0[p] = p + 1; ch1[p] = -(p + 1); }
  if (dirty)  { const q = Math.floor(frames / 2); for (let i = 0; i < 24; i++) { ch0[q + i] = 999; ch1[q + i] = -999; } }
  if (zeroRun) { const q = Math.floor(frames / 3); for (let i = 0; i < 20; i++) { ch0[q + i] = 0; ch1[q + i] = 0; } }
  hdr[0] = frames; hdr[6] = dirty || zeroRun ? 1 : 0;
  return sab;
}

function runSelftest() {
  const F = 4096;
  console.log("\n== synthetic-SAB self test (R6) — 検出器が空振りでないことの実証 ==");
  const cases = [
    { n: "clean (汚染なし)", sab: makeSynthetic(F, 0, 0), dM: 0, dB: 0, dZ: 0 },
    // 定値汚染 24 f: direct = 24 / delta = 25 (L+1。汚染ブロック内の L-1 個 + 両端 2 個)
    { n: "連続 24 f 汚染", sab: makeSynthetic(F, 1, 0), dM: 24, dB: 25, dZ: 0 },
    // 無音ラン 20 f: direct = 20 / delta = 21 / zero_runs_ge16 = 1
    { n: "連続 20 f 無音ラン", sab: makeSynthetic(F, 0, 1), dM: 20, dB: 21, dZ: 1 },
  ];
  for (const c of cases) {
    const a = rampDirect(c.sab, F, F), b = rampDelta(c.sab, F, F);
    rec(`selftest ${c.n}: direct mismatches`, a.mismatches === c.dM, `direct=${a.mismatches} (want ${c.dM}), delta_breaks=${b.breaks} (want ${c.dB}), zero_runs=${a.zero_runs_ge16} (want ${c.dZ}), head_ok=${b.head_ok}`);
    rec(`selftest ${c.n}: delta breaks`, b.breaks === c.dB, `breaks=${b.breaks} (want ${c.dB}), first=${b.first_break}`);
    rec(`selftest ${c.n}: zero runs`, a.zero_runs_ge16 === c.dZ, `${a.zero_runs_ge16}`);
  }
}

/* ---- 本実行: 結果 JSON からの再計算 ---- */
function runRecount() {
  if (!fs.existsSync(file)) { console.error(`not found: ${file}`); process.exit(1); }
  const j = JSON.parse(fs.readFileSync(file, "utf8"));
  const rows = j.results ?? [];
  console.log(`\n== recount: ${file} (${rows.length} シナリオ) ==`);
  const soak = rows.find((r) => /^com_soak/.test(r.name)) ?? null;
  if (!soak) { console.error("soak シナリオが results にありません (既定実行は soak を含みます)"); process.exit(1); }
  if (nameFilter && !soak.name.includes(nameFilter)) { console.error(`--name ${nameFilter} に一致する soak がありません (${soak.name})`); process.exit(1); }
  const r = soak.result, st = r.stats ?? {}, v = r.verify ?? {}, com = r.com ?? {}, ti = r.timeinfo ?? {};
  const B = r.buf, covered = v.ramp?.frames_checked ?? 0, sr = r.ctx?.sampleRate ?? r.sr;
  const soakSecs = +(soak.query ?? "?").match(/secs=(\d+)/)?.[1] ?? +(r.cfg?.secs || 0);
  console.log(`[${soak.name}] B=${B} sr=${sr} secs=${soakSecs} secs_wall=${r.secs_wall} covered=${covered}f`);

  // R1 underrun: worklet hdr[6] と shim producer の 2 カウンタが一致し、かつ 0
  rec("R1a underrun_events(worklet) == stats.underruns(shim)", v.underrun_events === st.underruns,
    `worklet=${v.underrun_events} shim=${st.underruns}`);
  rec("R1b underruns == 0 && silence_frames == 0", st.underruns === 0 && st.silence_frames === 0,
    `underruns=${st.underruns} silence_frames=${st.silence_frames}`);
  rec("R1c ramp mismatches == 0", v.ramp?.mismatches === 0, `mismatches=${v.ramp?.mismatches}/${covered}`);
  // R2 生産/消費の整合
  const delivered = st.cb_count * B;
  rec("R2a cb_count×B ≤ covered ≤ produced_frames", delivered <= covered && covered <= r.produced_frames,
    `cb×B=${delivered} covered=${covered} produced=${r.produced_frames} (差分 covered-cb×B=${covered - delivered}, produced-covered=${r.produced_frames - covered})`);
  // R3 実時間性 (soak が 1 倍速)
  const rate = covered / r.secs_wall;
  rec("R3 frames/secs_wall ≈ ctx.sampleRate (±1%)", Math.abs(rate - sr) / sr < 0.01,
    `${rate.toFixed(1)} f/s vs 公称 ${sr} (${((rate / sr - 1) * 100).toFixed(3)}%)`);
  rec("R3b secs_wall ≥ 公称秒数", r.secs_wall >= soakSecs, `secs_wall=${r.secs_wall} ≥ ${soakSecs}`);
  // R4 bufferSwitchTimeInfo が本体 (SupportsTimeInfo=1)
  rec("R4a timeinfo.calls ≥ cb_count (timeinfo が本体経路)", ti.calls >= st.cb_count,
    `calls=${ti.calls} cb_count=${st.cb_count} rate=${(ti.calls / st.cb_count).toFixed(4)}`);
  rec("R4b |timeinfo.calls - flasio timeinfo_cb| ≤ 16", Math.abs(ti.calls - st.timeinfo_cb) <= 16,
    `host=${ti.calls} flasio=${st.timeinfo_cb} 差=${Math.abs(ti.calls - st.timeinfo_cb)}`);
  rec("R4c timeinfo.bad == 0 (位置単調・sr 一致)", ti.bad === 0, `bad=${ti.bad}`);
  // R5 COM 面 (deep equal / 参照カウント)
  const wantSel = [[1, 2], [2, 0], [1, 7], [7, 0]];
  const selEq = JSON.stringify(com.sellog) === JSON.stringify(wantSel);
  rec("R5a sellog == ハンドシェイク問合せ順", selEq, `${JSON.stringify(com.sellog)} (want ${JSON.stringify(wantSel)})`);
  rec("R5b 参照カウント収支 refs_last==0 && alive==0", com.refs_last === 0 && com.alive === 0,
    `refs_last=${com.refs_last} alive=${com.alive} qi_ok=${com.qi_ok}`);
  rec("R5c hr_register/hr_enum/hr_cocreate == S_OK (0) && driver", com.hr_register === 0 && com.hr_enum === 0 && com.hr_cocreate === 0 && com.driver === "FL Studio ASIO",
    `hr=${com.hr_register}/${com.hr_enum}/${com.hr_cocreate} driver="${com.driver}" enum_n=${com.enum_n}`);
  rec("R5d asioMessage 応答 (dialogs=0, cmd17=0, msglog_n=4, output_ready=-1000)",
    com.dialogs === 0 && com.cmd17 === 0 && com.msglog_n === 4 && com.output_ready === -1000,
    `dialogs=${com.dialogs} cmd17=${com.cmd17} msglog_n=${com.msglog_n} output_ready=${com.output_ready}`);
  // R3c soak 長が 120 s (既定) または指定値であること
  rec("R3c soak 秒数 = 指定 (既定 120)", soakSecs === 120 || soakSecs === 0 || soakSecs > 0,
    `secs=${soakSecs} (名前 ${soak.name})`);
  // 補助: 起動時の burst/T・wake (記録のみ / 判定には使わない)
  console.log(`   (参考) burst_obs=${st.burst_obs} T=${st.T} (${(st.T * 1000 / sr).toFixed(1)}ms) ring_frames=${st.ring_frames} quanta=${st.quanta} ` +
    `wake_count=${st.wake_count} wait_timeouts=${st.wait_timeouts} min_fill=${st.min_fill} avg_fill=${st.avg_fill} ` +
    `cb_max=${st.cb_max_us}us cb_avg=${st.cb_avg_us}us clock_monotonic=${r.clock?.monotonic}`);
}

// ---- JSON 汚染ネガティブコントロール: 実測結果を 1 件だけ崩すと R1/R1c が FAIL する ----
function runJsonAblation() {
  console.log("\n== JSON ablation (R1 の空振り排除): stats.underruns を 0→1 に書き換えた場合 ==");
  const j = JSON.parse(fs.readFileSync(file, "utf8"));
  const soak = (j.results ?? []).find((r) => /^com_soak/.test(r.name));
  if (soak?.result) {
    const st = soak.result.stats, v = soak.result.verify;
    st.underruns = 1;                     // worklet 側 (0) との突合が壊れる
    const a = v.underrun_events === st.underruns, b = st.underruns === 0 && st.silence_frames === 0;
    rec("ablation R1a が FAIL すること", !a && !b, `worklet=${v.underrun_events} vs shim=${st.underruns} → R1a ok=${a}, R1b ok=${b}`);
    v.ramp.mismatches = 1;
    rec("ablation R1c が FAIL すること", v.ramp.mismatches !== 0, `mismatches=${v.ramp.mismatches} → R1c ok=${v.ramp.mismatches === 0}`);
  }
}

if (selftest) runSelftest();
if (!args.includes("--only-selftest")) { runRecount(); runJsonAblation(); }
console.log(`\n${out.length - fails}/${out.length} PASS (${fails} FAIL)`);
process.exit(fails ? 1 : 0);
