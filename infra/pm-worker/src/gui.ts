// GET / の簡易 GUI (#2658)。単一 HTML を Worker のソースに文字列として内包する (ビルド工程・外部リソースなし)。
// 画面は同一オリジンの GET /status を 15 秒ごとに読み、値は textContent だけで描く (innerHTML 等は使わない)。
// この Worker は App の秘密鍵を持つ制御面なので、外部から script / style / font / image を読み込まない (CSP の default-src 'none')。
// script と style は応答ごとの nonce で許可する (インラインの style 属性は使わず、幅などは CSSOM で設定する)。
import { randomToken } from "./crypto.ts";

export const GUI_HTML = `<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>signature-studio-pm 状態</title>
<style nonce="__NONCE__">
:root{color-scheme:light dark;--bg:#f5f6f8;--card:#fff;--fg:#1d2330;--mut:#667085;--line:#d9dde5;--ok:#15803d;--warn:#a16207;--bad:#b91c1c;--off:#64748b;--bar:#3b82f6;--tgt:#111827}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a21;--fg:#e6e9ef;--mut:#9aa3b2;--line:#2c3342;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;--off:#94a3b8;--bar:#60a5fa;--tgt:#f9fafb}}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;background:var(--bg);color:var(--fg);overflow-wrap:anywhere}
main{max-width:1200px;margin:0 auto;padding:12px;display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr))}
.wide{grid-column:1/-1}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;min-width:0}
h1{font-size:18px;margin:0 0 2px}
h2{font-size:13px;margin:0 0 6px;color:var(--mut);font-weight:600}
.sub{margin:4px 0;color:var(--mut);font-size:12px}
.badges{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.badge{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;border:1px solid var(--line);color:var(--off)}
.badge.ok{border-color:var(--ok);color:var(--ok)}
.badge.warn{border-color:var(--warn);color:var(--warn)}
.badge.bad{border-color:var(--bad);color:var(--bad);font-weight:600}
.band{background:var(--bad);color:#fff;padding:8px 12px;border-radius:8px;font-weight:600;margin:8px 0}
.cfg{background:var(--warn);color:#fff;padding:8px 12px;border-radius:8px;font-weight:600;margin:8px 0}
.cfg a{color:#fff}
.kv{display:grid;grid-template-columns:1fr auto;gap:0 10px;padding:5px 0;border-top:1px dashed var(--line)}
.kv .k{color:var(--fg)}
.kv .s{grid-column:1/-1;color:var(--mut);font-size:11px;word-break:break-all}
.v{font-variant-numeric:tabular-nums;text-align:right}
.v.ok{color:var(--ok)}
.v.warn{color:var(--warn)}
.v.bad{color:var(--bad);font-weight:600}
.big{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;margin:2px 0 6px}
.big.bad{color:var(--bad)}
.d{color:var(--ok);font-size:12px;margin-left:4px}
.track{position:relative;display:block;height:10px;background:var(--line);border-radius:5px;margin:6px 0}
.fill{display:block;height:100%;width:0;background:var(--bar);border-radius:5px}
.fill.bad{background:var(--bad)}
.fill.warn{background:var(--warn)}
.tgt{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--tgt);left:0}
.catrow{display:grid;grid-template-columns:1fr auto;gap:0 8px;padding-top:4px}
.catrow .cn{text-align:right;font-variant-numeric:tabular-nums}
.catrow .cn.warn{color:var(--warn);font-weight:600}
.catrow .track{grid-column:1/-1;margin:3px 0 4px}
a{color:var(--bar)}
button{font:inherit;padding:3px 10px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
details{margin-top:6px}
pre{white-space:pre-wrap;overflow:auto;max-height:50vh;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px;font-size:12px;margin:6px 0 0}
</style>
</head>
<body>
<noscript><p class="card wide">この画面は JavaScript で /status を読みます。JavaScript を有効にしてください。</p></noscript>
<main>
<header class="card wide">
<h1>signature-studio-pm</h1>
<p class="sub">Signature Studio の PM Worker の状態 (<span>/status</span> の表示)。PM bot: <span id="v-pm_bot_login">—</span></p>
<div class="badges">
<span class="badge" id="b-mode">mode</span>
<span class="badge" id="b-launch">launch</span>
<span class="badge" id="b-dispatch">dispatch</span>
<span class="badge" id="b-fresh">fresh</span>
<span class="badge" id="b-phase">phase</span>
<span class="badge" id="b-stop">launch_stop</span>
</div>
<p class="cfg" id="cfg" hidden>GitHub App が未設定です。<a href="/setup">/setup</a> を開いて作成してください (未設定の間は webhook も launch も動きません)。</p>
<p class="band" id="band" role="alert" hidden><span id="band-msg"></span></p>
<p class="sub">データ取得 (ブラウザの時刻): <span id="updated">—</span> · 15 秒ごとに更新 (タブが非表示の間は止めます)</p>
</header>

<section class="card">
<h2>鮮度 (freshness)</h2>
<div class="kv"><span class="k">last_tick 最終 tick</span><span class="v" id="v-last_tick">—</span><span class="s" id="s-last_tick">—</span></div>
<div class="kv"><span class="k">last_dispatch_at 最終 dispatch</span><span class="v" id="v-last_dispatch_at">—</span><span class="s" id="s-last_dispatch_at">—</span></div>
<div class="kv"><span class="k">last_webhook_at 最終 webhook</span><span class="v" id="v-last_webhook_at">—</span><span class="s" id="s-last_webhook_at">—</span></div>
<div class="kv"><span class="k">last_full_sync 全体同期</span><span class="v" id="v-last_full_sync">—</span><span class="s" id="s-last_full_sync">—</span></div>
<div class="kv"><span class="k">last_reconcile 差分同期</span><span class="v" id="v-last_reconcile">—</span><span class="s" id="s-last_reconcile">—</span></div>
<div class="kv"><span class="k">last_watchdog 監視 dispatch</span><span class="v" id="v-last_watchdog">—</span><span class="s" id="s-last_watchdog">—</span></div>
</section>

<section class="card">
<h2>容量 (同時実行 run)</h2>
<p class="big" id="cap-n">—</p>
<span class="track"><span class="fill" id="cap-bar"></span><span class="tgt" id="cap-tgt"></span></span>
<div class="kv"><span class="k">active_impl 実装 run</span><span class="v" id="v-active_impl">—</span></div>
<div class="kv"><span class="k">active_other その他 run</span><span class="v" id="v-active_other">—</span></div>
<div class="kv"><span class="k">queued 待機中</span><span class="v" id="v-queued">—</span></div>
<div class="kv"><span class="k">room 空き枠</span><span class="v" id="v-room">—</span></div>
<div class="kv"><span class="k">target 目標 (目盛り)</span><span class="v" id="v-target">—</span></div>
<div class="kv"><span class="k">target_eff 推定込みの目標</span><span class="v" id="v-target_eff">—</span></div>
</section>

<section class="card">
<h2>issue の区分</h2>
<div id="cats"></div>
<div class="kv"><span class="k">ready_by_prio 着手待ちの区分 (critical / normal / low)</span><span class="v" id="v-ready_by_prio">—</span></div>
<div class="kv"><span class="k">active_by_prio 実行中の run の区分 (critical / normal / low)</span><span class="v" id="v-active_by_prio">—</span></div>
<div class="kv"><span class="k">low_cap prio:low の上限 (cap / running / applied)</span><span class="v" id="v-low_cap">—</span></div>
</section>

<section class="card">
<h2>PR</h2>
<div class="kv"><span class="k">open_prs open の PR</span><span class="v" id="v-open_prs">—</span></div>
<div class="kv"><span class="k">open_prs_excl_stuck 停滞を除く</span><span class="v" id="v-open_prs_excl_stuck">—</span></div>
<div class="kv"><span class="k">stuck_prs 停滞 PR</span><span class="v" id="v-stuck_prs">—</span></div>
</section>

<section class="card">
<h2>カウンタ (ブラウザ内の前回取得との差分)</h2>
<div class="kv"><span class="k">launched 投稿</span><span class="v"><span id="v-c-launched">—</span><span class="d" id="d-c-launched"></span></span></div>
<div class="kv"><span class="k">dispatched 送信</span><span class="v"><span id="v-c-dispatched">—</span><span class="d" id="d-c-dispatched"></span></span></div>
<div class="kv"><span class="k">pmDispatched oc-pm 送信</span><span class="v"><span id="v-c-pmDispatched">—</span><span class="d" id="d-c-pmDispatched"></span></span></div>
<div class="kv"><span class="k">wouldLaunch 投稿予定 (dry-run)</span><span class="v"><span id="v-c-wouldLaunch">—</span><span class="d" id="d-c-wouldLaunch"></span></span></div>
<div class="kv"><span class="k">wouldDispatch 送信予定 (dry-run)</span><span class="v"><span id="v-c-wouldDispatch">—</span><span class="d" id="d-c-wouldDispatch"></span></span></div>
<div class="kv"><span class="k">reconciles 差分同期</span><span class="v"><span id="v-c-reconciles">—</span><span class="d" id="d-c-reconciles"></span></span></div>
</section>

<section class="card">
<h2>GitHub REST (残量)</h2>
<p class="big" id="rest-n">—</p>
<span class="track"><span class="fill" id="rest-bar"></span></span>
<div class="kv"><span class="k">rest_used 使用数</span><span class="v" id="v-rest_used">—</span></div>
<div class="kv"><span class="k">rest_reset_at 再設定</span><span class="v" id="v-rest_reset_at">—</span><span class="s" id="s-rest_reset_at">—</span></div>
</section>

<section class="card">
<h2>同期</h2>
<div class="kv"><span class="k">sync_truncated 打ち切り</span><span class="v" id="v-sync_truncated">—</span></div>
<div class="kv"><span class="k">reconcile_diff 差分の件数</span><span class="v" id="v-reconcile_diff">—</span></div>
<div class="kv"><span class="k">last_full_sync_rest_calls 全体同期の REST 呼び出し</span><span class="v" id="v-last_full_sync_rest_calls">—</span></div>
<div class="kv"><span class="k">comment_window_h コメントの窓 (時間)</span><span class="v" id="v-comment_window_h">—</span></div>
</section>

<section class="card">
<h2>PM agent / 再着手</h2>
<div id="pm-detected"></div>
<div class="kv"><span class="k">relaunch 再着手待ち</span><span class="v" id="v-relaunch">—</span></div>
<div class="kv"><span class="k">running 実行中 (状態別)</span><span class="v" id="v-running">—</span></div>
<div class="kv"><span class="k">dry_run_skipped_posts 書かずに捨てた件数</span><span class="v" id="v-dry_run_skipped_posts">—</span></div>
</section>

<footer class="wide">
<p class="sub"><a href="/status">/status (JSON)</a> · <a href="https://github.com/signature-studio/signature-studio-dev">signature-studio/signature-studio-dev</a></p>
<details>
<summary>生の JSON</summary>
<p class="sub" id="unknown">—</p>
<button type="button" id="copy">コピー</button>
<pre id="raw">—</pre>
</details>
</footer>
</main>
<script nonce="__NONCE__">
(function () {
  "use strict";
  var CAP = 60;
  var RATE_MAX = 5000;
  var POLL_MS = 15000;
  var TICK_STALE_MS = 180000;
  var WEBHOOK_STALE_MS = 1800000;
  var CATS = [
    ["ready", "着手待ち"], ["started", "着手済み"], ["blocked", "依存待ち"], ["user", "人の判断"],
    ["stopped", "停止"], ["recent", "直後"], ["hold", "保留"], ["killed_stopped", "kill 停止"]
  ];
  var COUNTERS = ["launched", "dispatched", "pmDispatched", "wouldLaunch", "wouldDispatch", "reconciles"];
  var PLAIN = [
    "active_impl", "active_other", "queued", "room", "target", "target_eff", "open_prs", "open_prs_excl_stuck",
    "rest_used", "last_full_sync_rest_calls", "comment_window_h", "relaunch", "dry_run_skipped_posts"
  ];
  var KNOWN = [
    "mode", "mode_launch", "mode_dispatch", "configured", "pm_bot_login", "fresh", "phase", "launch_stop",
    "last_tick", "last_dispatch_at", "last_webhook_at", "last_full_sync", "last_reconcile", "last_watchdog",
    "active_all", "active_runs", "active_impl", "active_other", "queued", "room", "target", "target_eff",
    "counters", "open_prs", "open_prs_excl_stuck", "stuck_prs", "rest_remaining", "rest_used", "rest_reset_at",
    "sync_truncated", "reconcile_diff", "last_full_sync_rest_calls", "comment_window_h", "pm_detected",
    "relaunch", "running", "dry_run_skipped_posts", "ready_by_prio", "active_by_prio", "low_cap"
  ].concat(CATS.map(function (c) { return c[0]; }));
  var last = null;
  var lastOk = 0;
  var failMsg = "";
  var prevCounters = null;
  var deltas = {};
  var pollT = null;
  var clockT = null;

  function $(id) { return document.getElementById(id); }
  function put(id, s, cls) {
    var el = $(id);
    el.textContent = s;
    if (cls !== undefined) el.className = cls;
  }
  function txt(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  }
  function fmtObj(o) {
    if (!o || typeof o !== "object") return txt(o);
    return Object.keys(o).map(function (k) { return k + " " + txt(o[k]); }).join(" · ");
  }
  function mk(tag, cls, s) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (s !== undefined) el.textContent = s;
    return el;
  }
  function setBar(el, pct, cls) {
    var p = typeof pct === "number" && pct === pct ? Math.max(0, Math.min(100, pct)) : 0;
    el.style.width = p + "%";
    el.className = "fill " + (cls || "");
  }
  function ms(iso) {
    var t = typeof iso === "string" ? Date.parse(iso) : NaN;
    return t;
  }
  function ago(iso, now) {
    var t = ms(iso);
    if (t !== t) return "—";
    var d = Math.max(0, Math.floor((now - t) / 1000));
    return Math.floor(d / 60) + "分" + (d % 60) + "秒前";
  }
  function until(iso, now) {
    var t = ms(iso);
    if (t !== t) return "—";
    var d = Math.max(0, Math.floor((t - now) / 1000));
    return "あと" + Math.floor(d / 60) + "分";
  }
  function row(key, iso, cls, now) {
    put("v-" + key, ago(iso, now), "v " + (cls || ""));
    put("s-" + key, txt(iso), "s");
  }
  function badge(id, cls, s) { put(id, s, "badge " + cls); }

  function paint(s) {
    var now = Date.now();
    badge("b-mode", s.mode === "live" ? "ok" : "warn", "mode: " + txt(s.mode));
    badge("b-launch", s.mode_launch === "live" ? "ok" : "warn", "launch: " + txt(s.mode_launch));
    badge("b-dispatch", s.mode_dispatch === "live" ? "ok" : "warn", "dispatch: " + txt(s.mode_dispatch));
    badge("b-fresh", s.fresh === true ? "ok" : s.fresh === false ? "bad" : "", "fresh: " + txt(s.fresh));
    badge("b-phase", "", "phase: " + txt(s.phase));
    if (s.launch_stop === null || s.launch_stop === undefined) badge("b-stop", "ok", "launch_stop: なし");
    else badge("b-stop", "bad", "launch_stop: " + txt(s.launch_stop));
    put("v-pm_bot_login", txt(s.pm_bot_login), "");
    $("cfg").hidden = s.configured !== false;

    var tick = now - ms(s.last_tick);
    row("last_tick", s.last_tick, tick !== tick || tick >= TICK_STALE_MS ? "bad" : "", now);
    row("last_dispatch_at", s.last_dispatch_at, "", now);
    row("last_webhook_at", s.last_webhook_at, now - ms(s.last_webhook_at) >= WEBHOOK_STALE_MS ? "warn" : "", now);
    row("last_full_sync", s.last_full_sync, "", now);
    row("last_reconcile", s.last_reconcile, "", now);
    row("last_watchdog", s.last_watchdog, "", now);

    var act = typeof s.active_all === "number" ? s.active_all : s.active_runs;
    var over = typeof act === "number" && act > CAP;
    put("cap-n", txt(act) + " / " + CAP, "big" + (over ? " bad" : ""));
    setBar($("cap-bar"), typeof act === "number" ? act / CAP * 100 : 0, over ? "bad" : "");
    $("cap-tgt").style.left = (typeof s.target === "number" ? Math.min(100, s.target / CAP * 100) : 0) + "%";
    PLAIN.forEach(function (k) { put("v-" + k, txt(s[k]), "v"); });

    var box = $("cats");
    box.textContent = "";
    var max = 1;
    CATS.forEach(function (c) {
      var v = s[c[0]];
      if (typeof v === "number" && v > max) max = v;
    });
    CATS.forEach(function (c) {
      var v = s[c[0]];
      if (v === undefined && (c[0] === "hold" || c[0] === "killed_stopped")) return;
      var noSupply = c[0] === "ready" && v === 0;
      var r = mk("div", "catrow");
      r.appendChild(mk("span", "", c[0] + " " + c[1] + (noSupply ? "（供給切れの注意）" : "")));
      r.appendChild(mk("span", "cn" + (noSupply ? " warn" : ""), txt(v)));
      var tr = mk("span", "track");
      var f = mk("span", "fill");
      setBar(f, typeof v === "number" ? v / max * 100 : 0, "");
      tr.appendChild(f);
      r.appendChild(tr);
      box.appendChild(r);
    });

    var stuck = typeof s.stuck_prs === "number" && s.stuck_prs > 0;
    put("v-stuck_prs", txt(s.stuck_prs), "v" + (stuck ? " bad" : ""));

    var c = s.counters && typeof s.counters === "object" ? s.counters : {};
    COUNTERS.forEach(function (k) {
      put("v-c-" + k, txt(c[k]), "v");
      put("d-c-" + k, deltas[k] ? "+" + deltas[k] : "", "d");
    });

    var rr = s.rest_remaining;
    var low = typeof rr === "number" && rr < 1000;
    put("rest-n", txt(rr) + " / " + RATE_MAX, "big" + (low ? " bad" : ""));
    setBar($("rest-bar"), typeof rr === "number" ? rr / RATE_MAX * 100 : 0, low ? "bad" : "");
    put("v-rest_reset_at", until(s.rest_reset_at, now), "v");
    put("s-rest_reset_at", txt(s.rest_reset_at), "s");

    var tr2 = Array.isArray(s.sync_truncated) ? s.sync_truncated : [];
    put("v-sync_truncated", tr2.length ? tr2.map(function (x) { return txt(x && x.name) + " " + txt(x && x.pages) + "ページ"; }).join(", ") : "なし", "v" + (tr2.length ? " warn" : ""));
    var rd = s.reconcile_diff;
    put("v-reconcile_diff", rd && typeof rd === "object" ? "直近 " + txt(rd.last) + " / 累計 " + txt(rd.total) : "—", "v");

    var pmBox = $("pm-detected");
    pmBox.textContent = "";
    var pd = s.pm_detected && typeof s.pm_detected === "object" ? s.pm_detected : {};
    var kinds = Object.keys(pd);
    if (kinds.length === 0) pmBox.textContent = "—";
    kinds.forEach(function (k) {
      var r = mk("div", "kv");
      r.appendChild(mk("span", "k", "pm_detected " + k));
      r.appendChild(mk("span", "v", txt(pd[k])));
      pmBox.appendChild(r);
    });
    put("v-running", fmtObj(s.running), "v");
    put("v-ready_by_prio", fmtObj(s.ready_by_prio), "v");
    put("v-active_by_prio", fmtObj(s.active_by_prio), "v");
    put("v-low_cap", fmtObj(s.low_cap), "v");
  }

  function band() {
    var b = $("band");
    b.hidden = !failMsg;
    put("band-msg", failMsg ? "取得失敗 (" + failMsg + ") · " + (lastOk ? Math.floor((Date.now() - lastOk) / 1000) + "秒前の値を表示しています" : "まだ値を取得できていません") : "");
  }

  function accept(j) {
    var cur = j.counters && typeof j.counters === "object" ? j.counters : {};
    deltas = {};
    if (prevCounters) {
      COUNTERS.forEach(function (k) {
        var d = typeof cur[k] === "number" && typeof prevCounters[k] === "number" ? cur[k] - prevCounters[k] : 0;
        if (d > 0) deltas[k] = d;
      });
    }
    prevCounters = cur;
    last = j;
    lastOk = Date.now();
    failMsg = "";
    var unk = Object.keys(j).filter(function (k) { return KNOWN.indexOf(k) < 0; });
    put("unknown", unk.length ? "未表示のキー: " + unk.join(", ") : "未表示のキーはありません", "sub");
    put("raw", JSON.stringify(j, null, 2));
    put("updated", new Date(lastOk).toLocaleTimeString("ja-JP"));
    paint(j);
    band();
  }

  function poll() {
    fetch("/status", { cache: "no-store", headers: { accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (j) {
        if (!j || typeof j !== "object") throw new Error("応答の形式が想定と違います");
        accept(j);
      })
      .catch(function (e) {
        failMsg = e && e.message ? String(e.message) : "通信エラー";
        band();
      });
  }

  function start() {
    if (pollT !== null) return;
    poll();
    pollT = setInterval(poll, POLL_MS);
    clockT = setInterval(function () {
      if (last) paint(last);
      band();
    }, 1000);
  }
  function stop() {
    if (pollT !== null) clearInterval(pollT);
    if (clockT !== null) clearInterval(clockT);
    pollT = null;
    clockT = null;
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") stop();
    else start();
  });
  $("copy").addEventListener("click", function () {
    var t = $("raw").textContent;
    if (navigator.clipboard) navigator.clipboard.writeText(t).catch(function () {});
  });
  if (document.visibilityState !== "hidden") start();
})();
</script>
</body>
</html>
`;

export const GUI_MAX_BYTES = 40 * 1024;

export function guiHeaders(nonce: string): Record<string, string> {
  return {
    "content-type": "text/html; charset=utf-8",
    "content-security-policy": `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}'; connect-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`,
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
  };
}

// GET / と HEAD /。nonce は応答ごとに暗号論的乱数で作る。他のメソッドは 405 (Allow: GET, HEAD)。
export function guiResponse(method: string): Response {
  if (method !== "GET" && method !== "HEAD") {
    return new Response("method not allowed", { status: 405, headers: { allow: "GET, HEAD", "cache-control": "no-store", "x-content-type-options": "nosniff" } });
  }
  const nonce = randomToken(16);
  const body = GUI_HTML.split("__NONCE__").join(nonce);
  return new Response(method === "HEAD" ? null : body, { status: 200, headers: guiHeaders(nonce) });
}
