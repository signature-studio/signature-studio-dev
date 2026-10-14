// シナリオ行列ランナー: 1 つの headless Chrome で全シナリオを順に実行し、結果 JSON と判定を出力する。
// 使い方: node harness/run.mjs [--quick] [--only name,name] [--out results/results.json]
//        node harness/run.mjs --soak30   # 30 分ソークのみ (AU-10)
import { withChrome } from "./chrome.mjs";
import path from "node:path"; import fs from "node:fs"; import os from "node:os"; import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const quick = args.includes("--quick");
const only = args.includes("--only") ? args[args.indexOf("--only") + 1].split(",") : null;
const S = (full, q) => (quick ? q : full);
// AU-10 (#191): 長時間ソーク。既定の全シナリオ実行には含めない (--soak30 / --soak <秒> 指定時のみ、そのシナリオだけを実行する)。
//   --soak30        : 1800 秒 (30 分) ランプ・ソーク (B=256, 48kHz, 全フレーム bit-exact 照合)
//   --soak <秒>     : 秒数指定 (短縮確認・ネガコン用)
//   --inject-hiccup : ネガティブコントロール。60ms の強制ブロックを混入し、gate が FAIL (exit 1) することを確認する用
const soakSecs = args.includes("--soak30") ? 1800 : args.includes("--soak") ? +args[args.indexOf("--soak") + 1] : 0;
if (args.includes("--soak") && !(soakSecs > 0)) { console.error("--soak には 1 以上の秒数が必要です"); process.exit(2); }
const injectHiccup = args.includes("--inject-hiccup");
if (injectHiccup && !(soakSecs > 0)) { console.error("--inject-hiccup は --soak30 / --soak <秒> と併用してください"); process.exit(2); }
// 既定の results/results.json (全シナリオの記録) を soak 単独実行で上書きしない: soak は results/soak_<秒>[_negctl].json
const outFile = args.includes("--out") ? args[args.indexOf("--out") + 1]
  : path.join(here, "../results", soakSecs > 0 ? `soak_${soakSecs}${injectHiccup ? "_negctl" : ""}.json` : "results.json");

// expect: 判定関数 (r) => [ok:boolean, msg]
const underrunFree = (r) => [r.stats.underruns === 0 && r.stats.silence_frames === 0, `underruns=${r.stats.underruns} silence=${r.stats.silence_frames}`];
const rampExact = (r) => [r.verify?.ramp && r.verify.ramp.mismatches === 0 && r.verify.ramp.frames_checked > 0, `ramp mismatches=${r.verify?.ramp?.mismatches}/${r.verify?.ramp?.frames_checked}`];
const sineOk = (r) => [r.verify?.sine && r.verify.sine.max_abs_err < 1e-5 && r.verify.sine.zero_runs_ge16 === 0, `sine maxErr=${r.verify?.sine?.max_abs_err?.toExponential(2)} rms=${r.verify?.sine?.rms?.toFixed(4)} zeroRuns=${r.verify?.sine?.zero_runs_ge16}`];
const dq = (v) => (v === undefined ? "-" : `${(v >>> 31) ? "-" : "+"}q${(v & 0x7fffffff) >>> 0}`);
const all = (...fs) => (r) => { const rs = fs.map((f) => f(r)); return [rs.every((x) => x[0]), rs.map((x) => x[1]).join("; ")]; };

const scenarios = [];
for (const buf of [128, 256, 512, 1024])
  scenarios.push({ name: `asio_ramp_b${buf}_d2`, q: `api=asio&mode=ramp&buf=${buf}&depth=2&secs=${S(20, 4)}`, expect: all(underrunFree, rampExact) });
scenarios.push({ name: "asio_sine_b256_d2", q: `api=asio&mode=sine&buf=256&depth=2&secs=${S(15, 4)}`, expect: all(underrunFree, sineOk) });
scenarios.push({ name: "asio_sine_b512_d4_44k", q: `api=asio&mode=sine&buf=512&depth=4&sr=44100&secs=${S(10, 4)}`, expect: all(underrunFree, sineOk) });
scenarios.push({ name: "asio_sine_b256_96k", q: `api=asio&mode=sine&buf=256&depth=2&sr=96000&secs=${S(10, 4)}`, expect: all(underrunFree, sineOk) });
// AU-11: 96kHz × B=512 (ILWASAPI preferred) は burst 2048〜4096 でも depth 12〜 で堅牢。B=256 は burst 4096 でも depth 21 で成功 (固定 depth 上限を撤廃)
scenarios.push({ name: "asio_sine_b512_96k", q: `api=asio&mode=sine&buf=512&depth=2&sr=96000&secs=${S(10, 4)}`, expect: all(underrunFree, sineOk) });
// burst を 4096 に強制 (OPEN 較正値の揺れを決定的に再現): B=256 → depth 21 で成功 (abort しない)
scenarios.push({ name: "asio_sine_b256_96k_burst4096", q: `api=asio&mode=sine&buf=256&depth=2&sr=96000&burst_floor=4096&secs=${S(10, 4)}`,
  expect: (r) => { const [a, m1] = all(underrunFree, sineOk)(r); return [a && !r.aborted && r.stats.T >= 5120, `${m1}; T=${r.stats.T} burst_obs=${r.stats.burst_obs}`]; } });
// ring に収まらない burst は abort でなく CreateBuffers が ASE_NoMemory(-994) を返し、その後の再 CreateBuffers が成功する
scenarios.push({ name: "asio_createbuffers_burst_overflow", q: "api=nomem&buf=256&sr=96000&burst_floor=40000&secs=1",
  expect: (r) => [!r.aborted && r.codes?.first === -994 && r.codes?.retry === 0 && r.codes?.dispose === 0, `first=${r.codes?.first}(want -994 ASE_NoMemory) retry=${r.codes?.retry}(want 0) dispose=${r.codes?.dispose}(want 0) aborted=${!!r.aborted}`] });
// 過負荷: 6 本の busy スレッド + main thread 30ms/100ms ブロック + コールバック毎 1.5ms 相当の演算。共有ホスト (load avg ~12/16コア) 上。
// 合格条件 = 「劣化しても連続性が保たれる」: underruns<=5 かつ復帰後 ramp[p-S] 完全一致 (underrun 件数自体は実測値として記録)
scenarios.push({ name: "asio_ramp_b256_load", q: `api=asio&mode=ramp&buf=256&depth=2&stress=6&jank=1&work_us=1500&secs=${S(20, 5)}`,
  expect: (r) => { const t = r.verify.ramp.tail_shift_exact; return [r.stats.underruns <= 5 && t.exact === t.checked && t.checked > 0 && r.workletErrors.length === 0,
    `過負荷: underruns=${r.stats.underruns} silence=${r.stats.silence_frames}f, 復帰後 ramp[p-S] 一致 ${t.exact}/${t.checked}`]; } });
// AU-7 (#193): FLEngine は systemTime だけを読み (ns→int32 ms)、timeGetTime() と同じ時間軸で扱う。ILWASAPI と同じ「コールバック時刻」規約なら
// d = systemTime_ms − timeGetTime() は {-1,0} (採取がコールバック直前)。可聴時刻規約 (FLASIO_SYSTIME_AUDIBLE=1) だと正の数十 ms / 起動直後は負の大値になり FAIL する
scenarios.push({ name: "asio_sine_b256_timeinfo", q: `api=asio&mode=sine&buf=256&depth=2&timeinfo=1&secs=${S(10, 4)}`,
  expect: (r) => { const [a, m1] = all(underrunFree, sineOk)(r); const t = r.timeinfo;
    return [a && t.calls > 0 && t.bad === 0 && r.stats.timeinfo_cb > 0 && t.calls >= r.stats.timeinfo_cb && t.calls - r.stats.timeinfo_cb <= 16
      && t.st_n === t.calls && t.st_invalid === 0 && t.st_nonmono === 0 && t.st_dmax <= 1 && t.st_dmin >= -5,
      `${m1}; bufferSwitchTimeInfo calls=${t.calls} bad=${t.bad}; systemTime(FL変換) valid=${t.st_n} invalid=${t.st_invalid} nonmono=${t.st_nonmono} d=[${t.st_dmin},${t.st_dmax}]ms`]; } });
// AU-7 (#193): 既定 profile = ILWASAPI (min256/max4096/pref512/gran0)。B=128 は profile の min 未満でも createBuffers は受理する (上の asio_ramp_b128_d2)
scenarios.push({ name: "asio_profile_ilwasapi_b512", q: `api=asio&mode=ramp&buf=512&depth=2&secs=${S(6, 4)}`,
  expect: (r) => { const p = r.reported; const ok = p.min === 256 && p.max === 4096 && p.pref === 512 && p.gran === 0 && p.nin === 2 && p.nout === 2 && p.ch_type === 19;
    const [a, m1] = all(underrunFree, rampExact)(r); return [ok && a, `reported min/max/pref/gran=${p.min}/${p.max}/${p.pref}/${p.gran} ch=${p.nin}/${p.nout} type=${p.ch_type}; ${m1}`]; } });
// AU-7 (#193): 起動直後 outputLatency=0 を FL (createBuffers 直後の getLatencies, 一度だけ) に読ませない。ATTACH が 0 の間待つ
scenarios.push({ name: "asio_outlat_zero_at_start_absorbed", q: `api=asio&mode=sine&buf=256&depth=2&olat_zero_ms=300&secs=${S(6, 4)}`,
  expect: (r) => { const p = r.reported; const [a, m1] = all(underrunFree, sineOk)(r);
    return [a && p.olat_us0 > 0 && p.lat_out0 > 0, `${m1}; createBuffers 直後 out_latency_us=${p.olat_us0} lat_out0=${p.lat_out0}f (終了時 ${p.lat_out}f)`]; } });
// 上と同条件で待ちを無効化 (旧挙動): FL が 0 を読む欠陥が再現することの確認 = 上の判定が空振りでないことのネガティブコントロール (期待: olat_us0 === 0)
scenarios.push({ name: "asio_outlat_zero_at_start_unabsorbed_control", q: `api=asio&mode=sine&buf=256&depth=2&olat_zero_ms=300&olat_wait_ms=0&secs=${S(6, 4)}`,
  expect: (r) => { const p = r.reported; return [p.olat_us0 === 0 && p.lat_out > p.lat_out0, `待ち無効: createBuffers 直後 out_latency_us=${p.olat_us0}(want 0) lat_out0=${p.lat_out0}f < 終了時 ${p.lat_out}f`]; } });
scenarios.push({ name: "asio_sine_b256_setsr_48k_to_44k", q: `api=asio&mode=sine&buf=256&depth=2&sr=48000&sr_after=44100&secs=${S(8, 4)}`,
  expect: (r) => { const [a, m1] = all(underrunFree, sineOk)(r); return [a && r.ctx.sampleRate === 44100 && r.rate_changes === 1, `${m1}; ctx.sampleRate=${r.ctx.sampleRate} sampleRateDidChange=${r.rate_changes}`]; } });
scenarios.push({ name: "asio_ramp_b256_hiccup", q: `api=asio&mode=ramp&buf=256&depth=2&hiccup_ms=60&hiccup_every=200&secs=${S(15, 6)}`,
  expect: (r) => { const t = r.verify.ramp.tail_shift_exact; return [r.stats.underruns > 0 && r.stats.silence_frames > 0 && t.exact === t.checked && t.checked > 0 && r.workletErrors.length === 0,
    `強制 60ms hiccup: underruns=${r.stats.underruns} silence=${r.stats.silence_frames}f → 復帰後 ramp[p-S] 一致 ${t.exact}/${t.checked}`]; } });
// AU-6 (#190): T の減衰。hiccup 期間に T を拡張 → hiccup 停止後 (安定 3s 毎に B 刻み) で T が元の下限 (T0) まで戻ること。
// 判定: 拡張が起き (grows>0, T_max > T0)、減衰が起き (shrinks>0)、終端 T は T0 (= depth0*B) に戻る。hiccup 無しの対照は T 不変。
scenarios.push({ name: "asio_shrink_after_hiccup_b256", q: `api=asio&mode=ramp&buf=256&depth=2&hiccup_ms=60&hiccup_every=200&hiccup_stop_ms=3000&secs=16`,
  expect: (r) => { const s = r.stats, t = r.verify.ramp?.tail_shift_exact ?? { exact: 0, checked: 0 };
    return [s.grows > 0 && s.shrinks > 0 && s.T_max > s.T0 && s.T === s.T0 && t.checked > 0 && t.exact === t.checked && r.workletErrors.length === 0,
      `grows=${s.grows} shrinks=${s.shrinks} T0=${s.T0} T_max=${s.T_max} T_end=${s.T}; 復帰後 ramp 一致 ${t.exact}/${t.checked}; underruns=${s.underruns}`]; } });
scenarios.push({ name: "asio_shrink_control_no_underrun_b256", q: `api=asio&mode=sine&buf=256&depth=2&secs=${S(8, 5)}`,
  expect: (r) => { const [a, m1] = all(underrunFree, sineOk)(r); const s = r.stats; return [a && s.grows === 0 && s.shrinks === 0 && s.T === s.T0, `${m1}; grows=${s.grows} shrinks=${s.shrinks} T=${s.T} T0=${s.T0}`]; } });
scenarios.push({ name: "asio_ramp_b256_suspend", q: `api=asio&mode=ramp&buf=256&depth=2&suspend=1&secs=${S(10, 5)}`,
  expect: (r) => [r.resets_seen >= 1 && r.workletErrors.length === 0, `kAsioResetRequest 受信=${r.resets_seen}, underruns=${r.stats.underruns}`] });
for (const buf of [128, 256, 512])
  scenarios.push({ name: `asio_loop_noise_b${buf}`, q: `api=asio&mode=loop&input=noise&buf=${buf}&depth=2&secs=${S(8, 5)}`,
    expect: (r) => [r.verify?.loop && r.verify.loop.best_norm_corr > 0.99 && r.stats.in_overruns === 0 && r.stats.underruns === 0, `lag=${r.verify?.loop?.lag_frames}f (${r.verify?.loop?.lag_ms?.toFixed(2)}ms) corr=${r.verify?.loop?.best_norm_corr?.toFixed(4)} in_overruns=${r.stats.in_overruns} in_underflows=${r.stats.in_underflows}`] });
scenarios.push({ name: "asio_loop_gum_fake_b256", q: `api=asio&mode=loop&input=gum&buf=256&depth=2&secs=${S(8, 5)}`,
  expect: (r) => [r.verify?.loop && r.verify.loop.input_rms > 1e-4 && r.workletErrors.length === 0, `gum input_rms=${r.verify?.loop?.input_rms?.toExponential(2)} corr=${r.verify?.loop?.best_norm_corr?.toFixed(3)} lag=${r.verify?.loop?.lag_frames}f tracks=${JSON.stringify(r.ctx?.gumTracks?.map((t) => t.label))}`] });
// AU-5 (#192): 入力デバイス UI。FlAudioInput 経由の入力接続 + controlPanel (ASIO::controlPanel) の UI 代替 + 入力喪失 → kAsioResetRequest
const loopOk = (r) => r.verify?.loop && r.verify.loop.input_rms > 1e-4 && r.verify.loop.best_norm_corr > 0.99 && r.workletErrors.length === 0;
scenarios.push({ name: "asio_input_ui_connect_b256", q: `api=asio&mode=loop&input=ui&buf=256&depth=2&secs=${S(8, 5)}`,
  expect: (r) => [loopOk(r) && r.stats.in_overruns === 0 && r.stats.reset_requests === 0, `FlAudioInput 接続 rms=${r.verify?.loop?.input_rms?.toExponential(2)} corr=${r.verify?.loop?.best_norm_corr?.toFixed(3)} lag=${r.verify?.loop?.lag_frames}f resets=${r.stats.reset_requests}`] });
scenarios.push({ name: "asio_input_ui_controlpanel_switch", q: `api=asio&mode=loop&input=ui&panel=1&buf=256&depth=2&secs=${S(8, 5)}`,
  expect: (r) => [loopOk(r) && r.panel_code === 0 && r.ui?.panelOpened === 1 && r.ui.controlPanelCalls === 1 && r.ui.switched && r.ui.switched !== r.ui.labels[0] && r.ui.permission === "granted",
    `controlPanel code=${r.panel_code}(want 0) opened=${r.ui?.panelOpened} 切替 ${JSON.stringify(r.ui?.labels)} devices=${r.ui?.devices?.length} rms=${r.verify?.loop?.input_rms?.toExponential(2)}`] });
scenarios.push({ name: "asio_controlpanel_no_ui", q: `api=asio&mode=loop&input=noise&panel=1&panel_ui=0&buf=256&depth=2&secs=${S(6, 4)}`,
  expect: (r) => [r.panel_code === -1000 && r.workletErrors.length === 0 && !r.aborted, `UI 未登録の controlPanel code=${r.panel_code}(want -1000 ASE_NotPresent)`] });
scenarios.push({ name: "asio_input_lost_reset", q: `api=asio&mode=loop&input=ui&lose=1&buf=256&depth=2&secs=${S(8, 5)}`,
  expect: (r) => [r.resets_seen >= 1 && r.stats.reset_requests >= 1 && r.ui?.events?.some((e) => e.type === "lost") && r.stats.underruns === 0 && r.workletErrors.length === 0,
    `入力喪失 → kAsioResetRequest 受信=${r.resets_seen} (stats ${r.stats.reset_requests}) lost=${JSON.stringify(r.ui?.events?.filter((e) => e.type === "lost"))} underruns=${r.stats.underruns}`] });
scenarios.push({ name: "asio_input_denied_output_ok", q: `api=asio&mode=loop&input=ui_denied&buf=256&depth=2&secs=${S(6, 4)}`,
  expect: (r) => [!r.aborted && r.stats.underruns === 0 && r.stats.cb_count > 0 && r.workletErrors.length === 0 && r.ui?.events?.some((e) => e.type === "permission" && e.state === "denied"),
    `権限拒否でも出力継続: cb=${r.stats.cb_count} underruns=${r.stats.underruns} events=${r.ui?.events?.filter((e) => e.type === "permission" || e.type === "error").map((e) => e.state ?? e.message)}`] });
scenarios.push({ name: "wasapi_ramp_b512_d2", q: `api=wasapi&mode=ramp&buf=512&depth=2&secs=${S(15, 4)}`, expect: all(underrunFree, rampExact) });
scenarios.push({ name: "wasapi_sine_b256_d3", q: `api=wasapi&mode=sine&buf=256&depth=3&secs=${S(10, 4)}`, expect: all(underrunFree, sineOk) });
if (!quick) scenarios.push({ name: "asio_ramp_b256_soak120", q: "api=asio&mode=ramp&buf=256&depth=2&secs=120", expect: all(underrunFree, rampExact) });

// ---- DirectSound (AU-4 #189): FL の呼出手順 (primary SetFormat 2 経路 = pcm16 / EXTENSIBLE float32、ポーリング / Notify) ----
// 合格 = underrun 0 + 出力 bit-exact + play/write cursor が整列・範囲内・単調 + write cursor が play の先 [P, T+2P] フレームに収まる
const dsCursor = (r) => { const c = r.cursor, T = r.stats.T, P = r.buf; return [c.backward_or_range_bad === 0 && c.write_ahead_min >= P && c.write_ahead_max <= T + 2 * P, `cursor bad=${c.backward_or_range_bad} write_ahead=${c.write_ahead_min}..${c.write_ahead_max}f (P=${P} T=${T})`]; };
const ramp16Exact = (r) => [r.verify?.ramp16 && r.verify.ramp16.mismatches === 0 && r.verify.ramp16.frames_checked > 0, `ramp16 mismatches=${r.verify?.ramp16?.mismatches}/${r.verify?.ramp16?.frames_checked}`];
const dsFmt = (tag, bits) => (r) => [r.reported.primary_tag === tag && r.reported.primary_bits === bits, `primary format tag=${r.reported.primary_tag} bits=${r.reported.primary_bits}`];
const dsNotifyRate = (r) => { const want = Math.floor(0.8 * r.cfg.secs * r.sr / (r.reported.size_frames / 2)); return [r.stats.notifies >= want && r.stats.notify_order_bad === 0, `notifies=${r.stats.notifies} (>=${want}) order_bad=${r.stats.notify_order_bad}`]; };
const dsWrap = (r) => [r.cursor.wraps_seen >= 1, `play cursor wraps=${r.cursor.wraps_seen}`];
scenarios.push({ name: "ds_pcm16_poll_ramp_b256", q: `api=ds&ds_fmt=pcm16&ds_mode=poll&buf=256&depth=2&secs=${S(15, 4)}`, expect: all(underrunFree, ramp16Exact, dsCursor, dsFmt(1, 16), dsWrap) });
scenarios.push({ name: "ds_pcm16_notify_ramp_b256", q: `api=ds&ds_fmt=pcm16&ds_mode=notify&buf=256&depth=2&secs=${S(15, 4)}`, expect: all(underrunFree, ramp16Exact, dsCursor, dsNotifyRate) });
scenarios.push({ name: "ds_f32_poll_ramp_b256", q: `api=ds&ds_fmt=f32&ds_mode=poll&mode=ramp&buf=256&depth=2&secs=${S(15, 4)}`, expect: all(underrunFree, rampExact, dsCursor, dsFmt(65534, 32), dsWrap) });
scenarios.push({ name: "ds_f32_notify_sine_b512", q: `api=ds&ds_fmt=f32&ds_mode=notify&mode=sine&buf=512&depth=2&secs=${S(10, 4)}`, expect: all(underrunFree, sineOk, dsCursor, dsNotifyRate) });
scenarios.push({ name: "ds_f32_poll_sine_b256_44k", q: `api=ds&ds_fmt=f32&ds_mode=poll&mode=sine&buf=256&depth=2&sr=44100&secs=${S(8, 4)}`, expect: all(underrunFree, sineOk, dsCursor) });
scenarios.push({ name: "ds_pcm16_notify_ramp_small4096", q: `api=ds&ds_fmt=pcm16&ds_mode=notify&ds_size=4096&buf=256&depth=2&secs=${S(8, 4)}`, expect: all(underrunFree, ramp16Exact, dsCursor, dsNotifyRate) });
// 過負荷 (asio_ramp_b256_load と同条件): 劣化しても連続性が保たれる = underruns<=5 かつ復帰後 ramp[p-S] 完全一致
scenarios.push({ name: "ds_f32_poll_ramp_b256_load", q: `api=ds&ds_fmt=f32&ds_mode=poll&mode=ramp&buf=256&depth=2&stress=6&jank=1&work_us=1500&secs=${S(20, 5)}`,
  expect: (r) => { const t = r.verify.ramp.tail_shift_exact; return [r.stats.underruns <= 5 && t.exact === t.checked && t.checked > 0 && r.workletErrors.length === 0,
    `過負荷: underruns=${r.stats.underruns} silence=${r.stats.silence_frames}f, 復帰後 ramp[p-S] 一致 ${t.exact}/${t.checked}`]; } });
// Stop でカーソル凍結・停止中のみ SetCurrentPosition 可・Play で再開 (pos は byte。S=16384f, blk=4 → 65536B)
scenarios.push({ name: "ds_stop_resume_cursor", q: `api=ds_stopresume&ds_fmt=pcm16&secs=${S(6, 4)}`,
  expect: (r) => { const [a, b, c, d] = r.pos; const HR_INVALIDCALL = -2005401550;
    const ok = a === b && c === 1024 * r.blk && d !== c && r.set_pos_stopped === 0 && r.set_pos_playing === HR_INVALIDCALL && r.status.idle === 0 && r.status.run === 5 && r.status.stop === 0;
    return [ok, `pos(stop,+400ms停止中,SetPos(1024f),再Play+400ms)=${r.pos.slice(0, 4)} SetPos再生中=${r.set_pos_playing}(want ${HR_INVALIDCALL}) status idle/run/stop=${r.status.idle}/${r.status.run}/${r.status.stop}`]; } });
scenarios.push({ name: "ds_apicheck", q: "api=ds_apicheck&secs=1",
  expect: (r) => { const c = r.codes ?? {}; const OK = 0, UNINIT = -2005401430, PRIO = -2005401530, BADFMT = -2005401500, ALLOC = -2005401590, INVCALL = -2005401550, INVPARAM = -2147024809;
    const want = { lock_nosec: UNINIT, coop_noinit: UNINIT, setfmt_noprim: INVCALL, prim: OK, prim_twice: ALLOC, setfmt_nopri: PRIO, setfmt_bad: BADFMT, setfmt_24: BADFMT, setfmt_ok: OK,
      hw: ALLOC, tiny: INVPARAM, odd: INVPARAM, nofmt: BADFMT, sec: OK, sec_twice: ALLOC, notify_nocaps: INVCALL, lock_wrap: OK, wrap_n1: 4, wrap_n2: 12, wrap_p2_is_base: 1,
      lock_twice: INVCALL, unlock_bad: INVPARAM, unlock_ok: OK, unlock_again: INVCALL, lock_oob: INVPARAM, lock_entire: OK, ent_n1: 65536,
      setpos_unaligned: INVPARAM, setpos_oob: INVPARAM, setpos_ok: OK, getpos: OK, play: 4096, write: 4096, getpos_null: OK, status: 0, stop_idle: OK, after_release: UNINIT };
    const bad = Object.keys(want).filter((k) => c[k] !== want[k]); return [bad.length === 0, bad.length ? "mismatch: " + bad.map((k) => `${k}=${c[k]}(want ${want[k]})`).join(", ") : `DS HRESULT/境界 ${Object.keys(want).length} 項目一致`]; } });
scenarios.push({ name: "failfast_ds_exclusive", q: "api=ff_ds_excl&secs=1", expect: (r) => [r.aborted && r.stderr.some((l) => l.includes("FAIL-FAST: flds_set_cooperative_level")), `abort stderr=${JSON.stringify(r.stderr?.filter((l) => l.includes("FAIL-FAST")))}`] });

// fail-fast / 戻り値検証 (AudioContext を開かない)
scenarios.push({ name: "failfast_asio_uninit", q: "api=ff_uninit&secs=1", expect: (r) => [r.aborted && r.stderr.some((l) => l.includes("FAIL-FAST: flasio_get_channels: driver not initialised")), `abort stderr=${JSON.stringify(r.stderr?.filter((l) => l.includes("FAIL-FAST")))}`] });
scenarios.push({ name: "failfast_wasapi_exclusive", q: "api=ff_excl&secs=1", expect: (r) => [r.aborted && r.stderr.some((l) => l.includes("FAIL-FAST: flwasapi_initialize")), `abort stderr=${JSON.stringify(r.stderr?.filter((l) => l.includes("FAIL-FAST")))}`] });
scenarios.push({ name: "asio_apicheck", q: "api=apicheck&secs=1",
  expect: (r) => { const c = r.codes ?? {}; const want = { createBuffers_100: -997, createBuffers_8192: -997, createBuffers_badch: -997, createBuffers_nullinfo: -998, setSampleRate_12345: -995,
    canSampleRate_44100: 0, getSamplePosition_stopped: -996, outputReady: -1000, future: -998, getChannelInfo_ch7: -998, setClockSource_1: -998, getClockSources: 0, clock_n: 1, start_nobuf: -997, getSampleRate: 0, rate: 48000 };
    const bad = Object.keys(want).filter((k) => c[k] !== want[k]); return [bad.length === 0, bad.length ? "mismatch: " + bad.map((k) => `${k}=${c[k]}(want ${want[k]})`).join(", ") : `ASIO エラーコード 16 項目一致`]; } });

if (soakSecs > 0) {
  scenarios.length = 0;
  const covered = (r) => { const want = Math.floor(soakSecs * (r.ctx?.sampleRate ?? 48000) * 0.99); const c = r.verify?.ramp?.frames_checked ?? 0; return [c >= want, `実フレーム ${c}f ≥ 公称 ${soakSecs}s の 99% (${want}f)`]; };
  const wall = (r) => [(r.secs_wall ?? 0) >= soakSecs, `secs_wall=${r.secs_wall} ≥ ${soakSecs}`];
  const noWorkletErr = (r) => [(r.workletErrors ?? []).length === 0 && !r.aborted && r.exit === 1, `workletErrors=${(r.workletErrors ?? []).length} aborted=${!!r.aborted} exit=${r.exit}(1=完了, 2=エラー)`];
  // 合格条件 (全て AND): underrun 0 / silence 0 / ランプ全フレーム bit-exact / 実フレーム ≥ 公称 99% / 実時間 ≥ 公称 / worklet エラー 0
  scenarios.push({ name: `asio_ramp_b256_soak${soakSecs}${injectHiccup ? "_negctl" : ""}`,
    q: `api=asio&mode=ramp&buf=256&depth=2&secs=${soakSecs}${injectHiccup ? "&hiccup_ms=60&hiccup_every=200" : ""}`,
    expect: all(underrunFree, rampExact, covered, wall, noWorkletErr) });
}
const sel = scenarios.filter((s) => !only || only.includes(s.name));
const loadStart = os.loadavg(), tStart = Date.now();
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
    if (r) {
      try { [ok, msg] = sc.expect(r); }
      catch (e) { ok = false; msg = r.aborted ? `想定外の abort: ${r.stderr?.find((l) => l.includes("FAIL-FAST")) ?? r.what}` : `expect 例外: ${e.message}`; }
    }
    if (!ok) failed++;
    results.push({ name: sc.name, query: sc.q, ok, msg, result: r ?? null, error: err });
    const st = r?.stats ?? {};
    if (r && (r.aborted || r.codes)) { console.log(`${ok ? "PASS" : "FAIL"} ${sc.name.padEnd(28)} ${msg}`); continue; }
    console.log(`${ok ? "PASS" : "FAIL"} ${sc.name.padEnd(28)} ${msg}` +
      (r ? `\n       clock_jump_log=${(r.clockJumpLog ?? []).map((e) => `q${e.q}:${e.d > 0 ? "+" : ""}${e.d}@f${e.frame}`).join(" ") || "-"}\n       cb=${st.cb_count ?? st.fills} late=${st.cb_late ?? "-"} cb_max=${st.cb_max_us ?? st.fill_max_us}us burst=${st.burst_obs ?? "-"} T=${st.T ?? "-"} (${st.T ? (st.T * 1000 / r.sr).toFixed(1) : "-"}ms) lat_changes=${st.latency_changes ?? "-"} wake_hist=${JSON.stringify(st.wake_hist)} ` +
        `dev_fill[min/avg/max]=${r.verify?.device_fill?.min}/${r.verify?.device_fill?.avg?.toFixed(0)}/${r.verify?.device_fill?.max} ` +
        `jumps=${r.snapshot?.clock_jumps}/${r.snapshot?.clock_jump_frames}f (skip=${r.snapshot?.clock_skip_frames}f dup=${r.snapshot?.clock_dup_frames}f max=${r.snapshot?.clock_jump_max}f@q${r.snapshot?.clock_jump_max_q} first=${dq(r.snapshot?.clock_first_q)} last=${dq(r.snapshot?.clock_last_q)}) cb_max_q=${r.snapshot?.cb_max_q ?? "-"} lat(in/out)=${r.reported?.lat_in ?? "-"}/${r.reported?.lat_out ?? "-"} clock=${r.clock?.rate_hz?.toFixed(1) ?? "-"}Hz` : ""));
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
const hostInfo = { load_start: loadStart, load_end: os.loadavg(), wall_s: (Date.now() - tStart) / 1000, nproc: os.cpus().length };
console.log(`host: load avg start=${loadStart.map((v) => v.toFixed(2))} end=${hostInfo.load_end.map((v) => v.toFixed(2))} wall=${hostInfo.wall_s.toFixed(1)}s nproc=${hostInfo.nproc}`);
fs.writeFileSync(outFile, JSON.stringify({ date: new Date().toISOString(), quick, chrome: "headless google-chrome 154", note: "ran_at は部分再実行時のシナリオ単位時刻", host: hostInfo, results: merged }, null, 1));
console.log(`\n${results.length - failed}/${results.length} PASS -> ${outFile}${only ? " (部分実行: 既存結果へマージ)" : ""}`);
process.exit(failed ? 1 : 0);
