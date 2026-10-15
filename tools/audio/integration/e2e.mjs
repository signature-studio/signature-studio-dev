#!/usr/bin/env node
// AU-9 ブラウザ e2e (e2e.sh から呼ばれる。AU9_ROOT = パッチ適用済みの検証ツリー)。
// 対象: dev サーバ / preview (vite build 成果物) の 2 構成 × 「クリック → shim 経由テスト音再生」。
// チェック: samplePos が 128f 単位で増加 / worklet 出力ダンプが 440/660Hz 理論値に一致 / underrun 0 / console error 無し。
// ネガティブコントロール: (N1) 期待周波数をずらすと照合が FAIL / (N2) テスト音 wasm 未配置だと状態表示が失敗になる。
import path from "node:path";
import { fileURLToPath } from "node:url";
import { rmSync } from "node:fs";
import { createServer, preview } from "vite";
import { launchChrome } from "../../runtime/lib/chrome.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = process.env.AU9_ROOT;
if (!root) throw new Error("AU9_ROOT 未設定 (e2e.sh 経由で実行)");
const results = [];
const rec = (name, ok, detail) => { results.push({ name, ok, detail }); console.log(`${ok ? "PASS" : "FAIL"} ${name}: ${detail}`); };
// producer の write 記録 (ctl.pw_trace) の要約。pw_at_underrun は underrun 直前の write と次の write (w/fill/起床µs/完了µs。w = 書き込み開始 frame)。
// 直近 FLA_PW_N 件の窓より前の失敗位置は out_of_window、窓内に直前の write が無いものは none、write が 1 件も無いものは no_writes。
// 差分は u32 の剰余 (>>> 0) で取る (起床・完了の µs は約 71.6 分で折り返すため)。
const pwInfo = (v) => {
  const pw = v.producer.writes;
  const n = v.producer.pw_n;
  if (pw.length === 0) return `pw_n=${n} pw_w_step=none pw_lat_max_us=none pw_gap_max_us=none${v.underrun_count ? " pw_at_underrun=[no_writes]" : ""}`;
  const lat = pw.map((e) => (e.done_us - e.wake_us) >>> 0);
  const gaps = pw.slice(1).map((e, i) => (e.wake_us - pw[i].wake_us) >>> 0);
  const steps = [...new Set(pw.slice(1).map((e, i) => (e.w - pw[i].w) >>> 0))];
  let at = -1;
  pw.forEach((e, i) => { if (v.first_underrun_frame >= 0 && e.w <= v.first_underrun_frame) at = i; });
  const atStr = at < 0
    ? (n > pw.length && v.first_underrun_frame < pw[0].w ? "out_of_window" : "none")
    : pw.slice(Math.max(0, at - 2), at + 2).map((e) => `${e.w}/${e.fill}/${e.wake_us}/${e.done_us}`).join(",");
  const stepStr = steps.length === 0 ? "none" : steps.length === 1 ? steps[0] : `mixed:${steps.join("|")}`;
  return `pw_n=${n} pw_w_step=${stepStr} pw_lat_max_us=${Math.max(...lat)} pw_gap_max_us=${gaps.length ? Math.max(...gaps) : "none"}${v.underrun_count ? ` pw_at_underrun=[${atStr}]` : ""}`;
};
// consumer (worklet) 側の underrun 通知の要約。先頭の通知 (cu[0]) の直近 6 quantum を p/rd/wr/wl/dms で出す (rd/wr は pw_at_underrun の w と同じ領域)。
// 通知は underrun ごとに先頭 8 件まで (worklet の TR_SEND)。通知の無い underrun は no_trace。
const cwInfo = (v) => {
  if (!v.underrun_count) return "cw_at_underrun=[none]";
  const cu = v.consumer ?? [];
  if (cu.length === 0) return "cw_at_underrun=[no_trace]";
  const u = cu[0];
  const tail = u.recs.slice(-6).map(([p, rd, wr, wl, dms]) => `${p}/${rd}/${wr}/${wl}/${dms}`).join(",");
  return `cw_p=${u.p} cw_consumed=${u.consumed} cw_rebuf=${u.rebuf} cw_notes=${cu.length} cw_at_underrun=[${tail}]`;
};
// keep-alive 接続 (Chrome 側) が残ると httpServer.close の callback が来ず永久に待つため、接続を強制切断してから閉じ、上限を付ける
const closeServer = async (srv, isDev) => {
  const closed = isDev ? srv.close() : new Promise((r) => srv.httpServer.close(r));
  if (!isDev) srv.httpServer.closeAllConnections();
  let to;
  const timedOut = await Promise.race([closed.then(() => false), new Promise((r) => { to = setTimeout(() => r(true), 10000); })]);
  clearTimeout(to);
  if (timedOut) console.log(`[au9] WARN: server close timed out after 10 s (dev=${isDev})`);
};

const chrome = await launchChrome();
const t0 = Date.now();
try {
  for (const mode of ["dev", "preview"]) {
    const srv = mode === "dev"
      ? await createServer({ root, logLevel: "warn", server: { port: 0, host: "127.0.0.1", strictPort: false } })
      : await preview({ root, logLevel: "warn", preview: { port: 0, host: "127.0.0.1", strictPort: false } });
    if (mode === "dev") await srv.listen();
    const port = srv.httpServer.address().port;
    const base = `http://127.0.0.1:${port}`;
    try {
      const page = await chrome.newPage(`${base}/?audio_capture=1`);
      const tag = (s) => `${mode}:${s}`;
      const st = `document.getElementById('status').textContent`;
      rec(tag("isolated"), (await page.evaluate("crossOriginIsolated")) === true, "crossOriginIsolated");
      await page.waitForExpr("document.getElementById('start-audio').disabled === false", 20000);
      await page.evaluate("document.getElementById('start-audio').click()");
      const pos = `(() => { const m = /samplePos=(\\d+)/.exec(${st}); return m ? +m[1] : -1; })()`;
      await page.waitForExpr(`${pos} > 0`, 30000);
      const p1 = await page.evaluate(pos);
      const tt = Date.now();
      await page.waitForExpr(`${pos} > ${p1} + 4800`, 20000);
      const p2 = await page.evaluate(pos);
      const rate = Math.round(((p2 - p1) / (Date.now() - tt)) * 1000);
      rec(tag("samplePos"), p1 % 128 === 0 && p2 % 128 === 0 && rate > 10000, `${p1} -> ${p2} (${rate} frames/s, 128f 単位)`);
      // 3 秒分以上ダンプされるまで待って照合
      await page.waitForExpr(`(window.__audio?.verify()?.covered_frames ?? 0) > 48000 * 3`, 30000);
      const v = await page.evaluate("window.__audio.verify()");
      const loc = `first_err_frame=${v.first_err_frame} first_zero_run_frame=${v.first_zero_run_frame} underrun_cap=${v.underrun_count} first_underrun_frame=${v.first_underrun_frame} last_underrun_frame=${v.last_underrun_frame} fill_at_first_underrun=${v.fill_at_first_underrun} fill_min_before_first_underrun=${v.fill_min_before_first_underrun} cb_gap_max_ms=${v.cb_gap_max_ms} cb_gap_over20=${v.cb_gap_over20_count} prod_wake_hist=${v.producer.wake_hist.join("/")} prod_wake_count=${v.producer.wake_count} prod_wait_timeouts=${v.producer.wait_timeouts} prod_cb_count=${v.producer.cb_count} prod_cb_max_us=${v.producer.cb_max_us} prod_cb_max_q=${v.producer.cb_max_q} ${pwInfo(v)} ${cwInfo(v)}${v.underrun_count ? ` fill_trace=[${v.fill_trace_before_first_underrun.join(",")}]` : ""}`;
      rec(tag("tone"), v.max_abs_err < 1e-5 && Math.abs(v.rms - 0.5 / Math.SQRT2) < 0.005 && v.zero_runs_ge16 === 0,
        `frames=${v.covered_frames} sr=${v.sampleRate} max_err=${v.max_abs_err.toExponential(2)} rms=${v.rms.toFixed(4)} (理論 0.3536) zero_runs=${v.zero_runs_ge16} peak=${v.peak.toFixed(3)} ${loc}`);
      rec(tag("underruns"), v.underruns === 0, `underruns=${v.underruns} ${loc}`);
      // N1: 期待周波数をずらした照合 (サンプルレートを 1% ずらす) は FAIL するはず
      const bad = await page.evaluate("window.__audio.verifyShifted(1.01)");
      rec(tag("neg1-shifted-rate"), bad.max_abs_err > 1e-3, `sr×1.01 で max_err=${bad.max_abs_err.toExponential(2)} (>1e-3 で検出)`);
      const errs = page.exceptions.slice();
      // index.ts の fail-fast フォワーダ疎通テストが意図的に出す 1 件 (tools/e2e/suite/checks.mjs console-clean と同じ許容) と favicon 404 のみ許容
      const allow = [/\[imports\] 未実装 import が呼ばれました: "shim_port\.not_implemented_yet"/, /favicon/];
      const logs = page.logs.filter((l) => (l.type === "error" || l.type === "warning") && !allow.some((a) => a.test(l.text)));
      rec(tag("console-clean"), errs.length === 0 && logs.length === 0, `exceptions=${errs.length} console err/warn=${logs.length}${logs.length ? " " + JSON.stringify(logs.slice(0, 3)) : ""}`);
    } finally {
      await closeServer(srv, mode === "dev");
    }
  }
  // N2: テスト音 wasm 未配置 (manifest 404) → 状態表示が「失敗」になり、ボタンが再度有効になる
  {
    rmSync(path.join(process.env.RUNTIME_WASM_DIR ?? path.join(root, "wasm"), "audio"), { recursive: true, force: true });
    const srv = await createServer({ root, logLevel: "warn", server: { port: 0, host: "127.0.0.1", strictPort: false } });
    await srv.listen();
    try {
      const page = await chrome.newPage(`http://127.0.0.1:${srv.httpServer.address().port}/`);
      await page.waitForExpr("document.getElementById('start-audio').disabled === false", 20000);
      await page.evaluate("document.getElementById('start-audio').click()");
      await page.waitForExpr("document.getElementById('status').textContent.includes('失敗')", 20000);
      const s = await page.evaluate("document.getElementById('status').textContent");
      rec("neg2-missing-wasm", /manifest 取得失敗/.test(s), s.slice(0, 120));
    } finally { await closeServer(srv, true); }
  }
} finally {
  await chrome.close();
}
const failed = results.filter((r) => !r.ok);
console.log(`\n[au9] ${results.length - failed.length}/${results.length} PASS, ${((Date.now() - t0) / 1000).toFixed(1)} s (here=${path.relative(process.cwd(), here)})`);
process.exit(failed.length ? 1 : 0);
