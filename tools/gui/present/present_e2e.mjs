#!/usr/bin/env node
// present_e2e.mjs — GUI-4 (#180) present 経路の e2e (FL / lift / wasm 不要; 模擬 guest で GuiShared を駆動)
//   golden  : 従来 CPU 経路 / WebGL2 経路 (direct・staged) / rAF+seqlock 経路の画面が、独立 oracle と毎ステップ画素一致 (差 0)
//   screen  : CDP スクリーンショット (ブラウザ合成後) も oracle と一致
//   tearing : seqlock off で tear が出る (陰性対照) / on で 0、最終フレームが必ず表示される
//   bench   : flush 時間 (CPU putImageData vs WebGL2) ※ headless Chrome の SwiftShader (ソフトウェア GL) であり実 GPU ではない
// 使い方: node tools/gui/present/present_e2e.mjs   (PRESENT_SKIP_BENCH=1 で bench 省略)
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { launchChrome } from "../../runtime/lib/chrome.mjs";
import { decodePNG } from "../../runtime/lib/png.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const GUI = path.join(HERE, "..");
const OUT = path.join(GUI, "build", "present");
fs.mkdirSync(OUT, { recursive: true });
const MIME = { ".js": "text/javascript", ".mjs": "text/javascript", ".html": "text/html" };
let failures = 0;
const ck = (name, ok, detail = "") => { console.log(`${ok ? "OK  " : "FAIL"} ${name}${detail ? "  — " + detail : ""}`); if (!ok) failures++; };
const range = (xs, d = 2) => (xs.length ? `${Math.min(...xs).toFixed(d)}–${Math.max(...xs).toFixed(d)}` : "n/a");

const roots = [["/js/", path.join(GUI, "build", "js")], ["/present/", HERE]];
const srv = http.createServer((req, res) => {
  let url = decodeURIComponent((req.url || "/").split("?")[0]);
  if (url === "/") url = "/present/index.html";
  const hit = roots.find(([p]) => url.startsWith(p));
  const headers = { "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp", "Cross-Origin-Resource-Policy": "same-origin", "Cache-Control": "no-store" };
  const file = hit && path.join(hit[1], url.slice(hit[0].length));
  if (!file || !file.startsWith(hit[1]) || !fs.existsSync(file)) { res.writeHead(404, headers); res.end("not found " + url); return; }
  res.writeHead(200, { ...headers, "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => srv.listen(0, "127.0.0.1", r));
const port = srv.address().port;

process.env.RUNTIME_TMP ||= process.env.RUNNER_TEMP || "/tmp/opencode";
const chrome = await launchChrome();
const load0 = os.loadavg()[0];
console.log(`[present-e2e] ${chrome.version} load=${load0.toFixed(2)} cpus=${os.cpus().length} node=${process.version}`);
const results = { chrome: chrome.version, loadStart: load0 };
try {
  const page = await chrome.newPage();
  await page.send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 720, deviceScaleFactor: 1, mobile: false });
  await page.send("Page.bringToFront");
  await page.goto(`http://127.0.0.1:${port}/`);
  const boot = await page.waitForExpr("window.__ready", 30000);
  ck("crossOriginIsolated (SAB)", boot.crossOriginIsolated === true);
  ck("requestAnimationFrame available in page", boot.rafType === "function");

  // ---------------- golden ----------------
  let t0 = Date.now();
  const g = await page.evaluate("window.__present.runGolden(45)", { timeout: 300000 });
  results.golden = { ...g, oracleB64: undefined };
  console.log(`[golden] ${g.steps} steps × ${g.W}x${g.H} px × ${g.results.length} renderers (${((Date.now() - t0) / 1000).toFixed(1)} s)`);
  for (const r of g.results) {
    const want = /gl/.test(r.name) ? "webgl2" : "2d";
    ck(`golden: ${r.name} backend=${r.info.backend} (want ${want})`, r.info.backend === want, `upload=${r.info.upload} sync=${r.info.sync} seqlock=${r.info.seqlock}`);
    ck(`golden: ${r.name} 画面 == oracle, ${r.steps} steps × ${g.W * g.H} px`, r.diffPx === 0, `差 ${r.diffPx} px${r.first ? " first=" + JSON.stringify(r.first) : ""}`);
  }
  ck("negative control: present 無しの 1 px 書換えを検出", g.negative.modifiedPixelDiff === 1, `差 ${g.negative.modifiedPixelDiff} px`);
  for (const s of g.stats) {
    const st = s.stats;
    console.log(`  stats ${s.name}: flushes=${st.flushes} frameEnds=${st.frameEnds} presents=${st.presents} → rects=${st.rects} (rectPx=${st.rectPixels}) fullRecompose=${st.fullRecomposes} raf=${st.rafFlushes} timer=${st.timerFlushes} imm=${st.immediateFlushes} seqRetry=${st.seqRetries} deferred=${st.seqDeferred} forced=${st.seqForced}` + (s.gl ? ` | gl uploads=${s.gl.uploads} uploadPx=${s.gl.uploadPixels} draws=${s.gl.draws} directFallback=${s.gl.directFallbacks}` : ""));
  }
  const gd = g.stats.find((s) => s.name.startsWith("gl-direct"));
  ck("dirty 複数矩形: 併合で rects < presents", gd.stats.rects < gd.stats.presents, `${gd.stats.presents} PRESENT → ${gd.stats.rects} 矩形`);
  const gr = g.stats.find((s) => s.name.startsWith("gl-staged-raf"));
  ck("rAF 同期: 全 flush が rAF 起動 (即時 flush 0・タイマ救済 0)", gr.stats.rafFlushes > 0 && gr.stats.immediateFlushes === 0 && gr.stats.timerFlushes === 0 && gr.stats.flushes === gr.stats.rafFlushes, `raf=${gr.stats.rafFlushes} timer=${gr.stats.timerFlushes} imm=${gr.stats.immediateFlushes} flushes=${gr.stats.flushes} frameEnds=${gr.stats.frameEnds}`);

  // ---------------- screenshot (ブラウザ合成後) ----------------
  const oracle = Buffer.from(g.oracleB64, "base64");
  for (const l of g.layout) {
    const shot = await page.send("Page.captureScreenshot", { format: "png", clip: { x: l.left, y: l.top, width: g.W, height: g.H, scale: 1 } });
    const png = decodePNG(Buffer.from(shot.data, "base64"));
    let diff = 0;
    for (let y = 0; y < g.H; y++) for (let x = 0; x < g.W; x++) {
      const o = (y * g.W + x) * 4, p = png.px(x, y);
      if (p[0] !== oracle[o] || p[1] !== oracle[o + 1] || p[2] !== oracle[o + 2]) diff++;
    }
    ck(`screenshot: ${l.name} == oracle`, png.w === g.W && png.h === g.H && diff === 0, `${png.w}x${png.h} 差 ${diff} px`);
    if (l.name.startsWith("gl-direct")) fs.writeFileSync(path.join(OUT, "screenshot_gl.png"), Buffer.from(shot.data, "base64"));
  }

  // ---------------- seqlock (決定的) ----------------
  const sd = await page.evaluate("window.__present.runSeqlockDet()", { timeout: 120000 });
  results.seqlockDet = sd;
  for (const v of sd) {
    console.log(`  seqlock-det ${v.name}: 書込み中の読出し=${v.duringShowsOld ? "旧フレーム維持" : v.duringShowsNew ? "新フレーム表示" : "不明"} deferred=${v.deferred} 静止後の収束=${v.converged} (${v.convergeMs} ms) forced=${v.forced}`);
    if (v.seqlock) ck(`seqlock: ${v.name} 書込み中は旧フレーム維持・静止後に新フレーム`, v.initialOk && v.duringShowsOld && !v.duringShowsNew && v.deferred >= 1 && v.converged && v.forced === 0);
    else ck(`seqlock 陰性対照: ${v.name} は書込み中でも新フレームを読む (= 保護なし)`, v.initialOk && v.duringShowsNew && v.deferred === 0);
  }

  // ---------------- tearing ----------------
  t0 = Date.now();
  const tr = await page.evaluate("window.__present.runTearing({frames: 90, periodMs: 16, rowWorkUs: 8})", { timeout: 300000 });
  results.tearing = tr;
  console.log(`[tearing] ${tr.frames} frames, guest ${tr.width}x${tr.height} 1 色/フレーム, period ${tr.periodMs} ms, 行あたり ${tr.rowWorkUs} µs (${((Date.now() - t0) / 1000).toFixed(1)} s)`);
  for (const v of tr.variants) {
    const st = v.stats;
    console.log(`  ${v.name}: flush 検査 ${v.acc.uniformChecked} 回中 tear 状態 ${v.acc.torn} 回 (発生 ${v.acc.tornEpisodes} 件) | deferred=${st.seqDeferred} retries=${st.seqRetries} forced=${st.seqForced} raf=${st.rafFlushes} timer=${st.timerFlushes} maxInflight=${v.guest.maxInflight} 最終フレーム表示=${v.finalFrameShown}`);
  }
  const off = tr.variants.filter((v) => /seqlock=off/.test(v.name)), on = tr.variants.filter((v) => /seqlock=on/.test(v.name));
  const offTorn = off.reduce((a, v) => a + v.acc.tornEpisodes, 0);
  console.log(`${offTorn >= 1 ? "OK  " : "WARN"} tearing 統計の対照: seqlock off で tear 観測 ${off.map((v) => `${v.name}=${v.acc.tornEpisodes}`).join(" ")} 件 (確率的; 決定的な陰性対照は seqlock-det)`);
  ck("tearing: seqlock on の tear 発生は強制読出し (飢餓回避) に由来するものだけ (発生件数 ≤ forced)", on.every((v) => v.acc.tornEpisodes <= v.stats.seqForced), on.map((v) => `${v.name}: 発生=${v.acc.tornEpisodes} forced=${v.stats.seqForced} deferred=${v.stats.seqDeferred}`).join(" | "));
  const offEp = off.reduce((a, v) => a + v.acc.tornEpisodes, 0), onEp = on.reduce((a, v) => a + v.acc.tornEpisodes, 0);
  ck("tearing: seqlock on の tear 発生件数 < off", onEp < offEp, `on=${onEp} off=${offEp}`);
  ck("tearing: seqlock on でも最終フレームが画面に出る", on.every((v) => v.finalFrameShown));
  ck("tearing: seqlock off でも最終フレームが画面に出る (対照)", off.every((v) => v.finalFrameShown));

  // ---------------- bench ----------------
  if (process.env.PRESENT_SKIP_BENCH !== "1") {
    t0 = Date.now();
    const b = await page.evaluate("window.__present.runBench({})", { timeout: 900000 });
    results.bench = b;
    console.log(`[bench] ${((Date.now() - t0) / 1000).toFixed(1)} s, frames=${b.frames} warm=${b.warm} reps=${b.reps} (min–max over reps; ms/frame)`);
    console.log("| size | dirty | config | flush(submit) ms | +GPU sync ms | wall ms/frame (ack) | rect/frame | Mpx/frame |");
    console.log("|---|---|---|---|---|---|---|---|");
    for (const r of b.results) {
      const sub = r.runs.map((x) => x.submitMs), gpu = r.runs.map((x) => x.syncedFlushMs + x.gpuSyncMs), wall = r.runs.map((x) => x.wallMs);
      console.log(`| ${r.size} | ${r.scenario} | ${r.config} | ${range(sub)} | ${r.backend === "webgl2" ? range(gpu) : "n/a"} | ${range(wall)} | ${r.runs[0].rectsPerFrame.toFixed(1)} | ${r.runs[0].mpixPerFrame.toFixed(3)} |`);
    }
  }
  const errs = page.exceptions.concat(page.logs.filter((l) => l.type === "error").map((l) => l.text));
  ck("page/worker に例外・console.error なし", errs.length === 0, errs.slice(0, 3).join(" | "));
} finally {
  results.loadEnd = os.loadavg()[0];
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 1));
  await chrome.close().catch(() => {});
  srv.close();
}
console.log(`[present-e2e] load ${results.loadStart.toFixed(2)} → ${results.loadEnd.toFixed(2)}; ${failures === 0 ? "ALL PASS" : failures + " FAILED"}`);
process.exit(failures === 0 ? 0 : 1);
