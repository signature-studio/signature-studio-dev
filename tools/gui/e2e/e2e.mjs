// e2e.mjs — headless Chrome E2E ドライバ (tools/e2e/suite/drivers 経由: 既定 agent-browser / E2E_DRIVER=puppeteer で CDP 直 puppeteer-core)
//   lifted Win32 app (wasm, pthread) + gui shim + gui.ts/gui_worker.ts (OffscreenCanvas) を実ブラウザで動かし、
//   実入力イベント (mouse down/move/up, key press) でシナリオを駆動、最終フレームを golden と比較する。
//   同期は全てイベント駆動 (page 内 waitLog/フレーム ack の Promise を eval で await)。固定 sleep なし。
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { BUILD, H, ROOT, W, decodePNG, diffRGB, openDriver, readPPM, startServer, writePPM } from "./e2e_lib.mjs";

const OUTDIR = path.join(BUILD, "e2e");
fs.mkdirSync(OUTDIR, { recursive: true });
const WATCHDOG_MS = Number(process.env.E2E_TIMEOUT_MS || 90000);

const log = (...a) => console.log("[e2e]", ...a);
const failures = [];
const need = (c, m) => { if (!c) { failures.push(m); console.error("[e2e] FAIL:", m); } };

let drv = null, srv = null;
const cleanup = async () => { try { await drv?.close(); } catch {} try { srv?.close(); } catch {} };
const wd = setTimeout(async () => {
  let tail = "";
  try { tail = (await drv.consoleMessages()).slice(-40).map((m) => m.text).join("\n  "); } catch {}
  console.error("[e2e] WATCHDOG timeout; console tail:\n  " + tail);
  await cleanup(); process.exit(3);
}, WATCHDOG_MS);

async function main() {
  const s = await startServer(); srv = s.srv;
  drv = await openDriver(`http://127.0.0.1:${s.port}/`);
  log("driver:", drv.name, drv.version);
  const E = (expr) => drv.eval(expr);
  const boot = await E("window.__ready");
  log("boot:", JSON.stringify(boot));
  need(boot.crossOriginIsolated === true, "crossOriginIsolated must be true (COOP/COEP)");
  need(boot.sab === true, "wasm memory must be SharedArrayBuffer");
  if (process.env.E2E_MODE === "w") {   // W 版ゲスト (test/gui_app_w.c): 入力なし。WM_PAINT 1 回 -> ESC で終了 (#3509)
    const L = (expr) => E(`window.__e2e.host.${expr}`);
    await L(`waitLog("w: roundtrip ok")`);
    log("W guest: WM_PAINT and SetWindowTextW/GetWindowTextW round trip done");
    // 期待画像は独立オラクル (golden/gen_golden_w.py; shim の C 実装と無関係)。E2E_TAMPER=1 では 1 画素改竄する
    const tamper = process.env.E2E_TAMPER === "1";
    const expFile = path.join(OUTDIR, tamper ? "w_expected_tamper.ppm" : "w_expected.ppm");
    execFileSync("python3", [path.join(ROOT, "golden", "gen_golden_w.py"), "emit", expFile, ...(tamper ? ["--tamper"] : [])], { stdio: "inherit" });
    const want = readPPM(expFile);
    const rb = await E(`(async () => { const r = await window.__e2e.host.readback(); let s = ""; const d = r.data; for (let i = 0; i < d.length; i += 0x8000) s += String.fromCharCode.apply(null, d.subarray(i, i + 0x8000)); return { w: r.width, h: r.height, b64: btoa(s) }; })()`);
    const rbuf = Buffer.from(rb.b64, "base64");   // RGBA (BGRA->RGBA 変換済み; worker)
    const gotPx = (x, y) => { const o = (y * rb.w + x) * 4; return [rbuf[o], rbuf[o + 1], rbuf[o + 2]]; };
    const d1 = diffRGB(want.data, W, H, gotPx);
    writePPM(path.join(OUTDIR, "w_canvas_readback.ppm"), W, H, gotPx);
    need(rb.w === W && rb.h === H, `readback size ${rb.w}x${rb.h}`);
    need(d1.diff === 0, `OffscreenCanvas readback != oracle: ${d1.diff} px differ, first=${JSON.stringify(d1.first)}`);
    log(`OffscreenCanvas readback vs oracle: ${d1.diff === 0 ? "EXACT MATCH" : "MISMATCH"} (${d1.diff} differing px of ${W * H})`);
    // 統計側で alpha を落として RGB 3 バイト列の sha256 を取る (gui_hl_stats の定義と同じ)。native は native_w_e2e.sh の surface 行
    const rgb = Buffer.alloc(W * H * 3);
    for (let i = 0; i < W * H; i++) { rgb[i * 3] = rbuf[i * 4]; rgb[i * 3 + 1] = rbuf[i * 4 + 1]; rgb[i * 3 + 2] = rbuf[i * 4 + 2]; }
    const sha = createHash("sha256").update(rgb).digest("hex");
    const nlog = fs.existsSync(path.join(BUILD, "native_w_run.log")) ? fs.readFileSync(path.join(BUILD, "native_w_run.log"), "utf8") : "";
    const nsha = /\[native_w_run\] surface .*sha256=([0-9a-f]{64})/.exec(nlog)?.[1];
    need(!!nsha, "native_w_run.log lacks the native surface sha256 (run tools/gui/test/native_w_e2e.sh first)");
    need(sha === nsha, `readback sha256 ${sha} != native surface sha256 ${nsha}`);
    log(`readback sha256 ${sha} vs native ${nsha}: ${sha === nsha ? "MATCH" : "MISMATCH"}`);
    const shotFile = path.join(OUTDIR, "w_screenshot.png");
    await drv.screenshot(shotFile);
    const png = decodePNG(fs.readFileSync(shotFile));
    const d2 = diffRGB(want.data, W, H, (x, y) => { const o = (y * png.w + x) * png.bpp; return [png.data[o], png.data[o + 1], png.data[o + 2]]; });
    need(png.w >= W && png.h >= H, `screenshot size ${png.w}x${png.h}`);
    need(d2.diff === 0, `screenshot != oracle: ${d2.diff} px differ, first=${JSON.stringify(d2.first)}`);
    log(`on-screen screenshot vs oracle: ${d2.diff === 0 ? "EXACT MATCH" : "MISMATCH"} (${d2.diff} differing px)`);
    await drv.press("Escape");
    await L(`waitLog("w: destroy")`);
    const code = await E(`window.__e2e.host.exited`);
    need(code === 0, `exit code ${code}`);
    log("W guest exited via ExitProcess, code=" + code);
    const errs = await E("window.__e2e.errors");
    need(errs.length === 0, "page errors: " + JSON.stringify(errs));
    const perr = await drv.pageErrors();
    need(perr.length === 0, "driver page errors: " + JSON.stringify(perr));
    return;
  }
  if (process.env.E2E_MODE === "failfast") {   // 未実装 API 到達 -> 即 abort + EXIT(0xFA11) が host に届くこと
    const code = await E("window.__e2e.host.exited");
    need(code === 0xFA11, `fail-fast exit code ${code} (want ${0xFA11})`);
    await E("new Promise((r) => setTimeout(r, 0))");
    const msgs = await drv.consoleMessages();
    need(msgs.some((m) => m.text.includes("FAIL-FAST: unimplemented Win32 API: Ellipse")), "console lacks FAIL-FAST message naming Ellipse");
    log(`fail-fast OK: host saw EXIT code 0x${code.toString(16)} and console named the API`);
    return;
  }
  const L = (expr) => E(`window.__e2e.host.${expr}`);
  const syncPaint = (ev) => L(`waitLog("paint ev=${ev}")`);

  const t0 = Date.now();
  await L(`waitLog("app: created")`);
  await L(`waitLog("app: timer-done")`);
  log("app created + SetTimer x3 -> KillTimer ok");
  const click = async (x, y, ev) => {
    await drv.mouse("move", x, y);
    await drv.mouse("down", x, y); await syncPaint(ev);
    await drv.mouse("up", x, y); await syncPaint(ev + 1);
  };
  await click(200, 150, 1);
  await click(210, 150, 3);
  await drv.mouse("move", 30, 150);
  await drv.mouse("down", 30, 150); await syncPaint(5);
  await drv.mouse("move", 100, 170); await syncPaint(6);
  await drv.mouse("move", 150, 180); await syncPaint(7);
  await drv.mouse("up", 150, 180); await syncPaint(8);
  for (const [ch, ev] of [["A", 9], ["b", 10]]) { await drv.press(ch); await syncPaint(ev); }
  log(`scenario complete in ${Date.now() - t0} ms`);

  // ---- 検証 1: OffscreenCanvas 読み戻し (worker) vs golden : exact ----
  const golden = readPPM(path.join(ROOT, "golden", "final.ppm"));
  if (process.env.E2E_TAMPER === "1") { golden.data = Buffer.from(golden.data); golden.data[(100 * W + 100) * 3] ^= 0xff; log("NEGCTL: golden を 1 画素改竄 (不合格が正しい挙動)"); }
  const rb = await E(`(async () => { const r = await window.__e2e.host.readback(); let s = ""; const d = r.data; for (let i = 0; i < d.length; i += 0x8000) s += String.fromCharCode.apply(null, d.subarray(i, i + 0x8000)); return { w: r.width, h: r.height, b64: btoa(s) }; })()`);
  const rbuf = Buffer.from(rb.b64, "base64");
  const gotPx = (x, y) => { const o = (y * rb.w + x) * 4; return [rbuf[o], rbuf[o + 1], rbuf[o + 2]]; };
  const d1 = diffRGB(golden.data, W, H, gotPx);
  writePPM(path.join(OUTDIR, "canvas_readback.ppm"), W, H, gotPx);
  need(rb.w === W && rb.h === H, `readback size ${rb.w}x${rb.h}`);
  need(d1.diff === 0, `OffscreenCanvas readback != golden: ${d1.diff} px differ, first=${JSON.stringify(d1.first)}`);
  log(`OffscreenCanvas readback vs golden: ${d1.diff === 0 ? "EXACT MATCH" : "MISMATCH"} (${d1.diff} differing px of ${W * H})`);

  // ---- 検証 2: 実画面 (ブラウザ合成後のスクリーンショット) vs golden ----
  //   viewport 480x360 の全体撮影から左上 320x200 を切り出す (canvas は left:0/top:0 固定)
  const shotFile = path.join(OUTDIR, "screenshot.png");
  await drv.screenshot(shotFile);
  const png = decodePNG(fs.readFileSync(shotFile));
  const d2 = diffRGB(golden.data, W, H, (x, y) => { const o = (y * png.w + x) * png.bpp; return [png.data[o], png.data[o + 1], png.data[o + 2]]; });
  need(png.w >= W && png.h >= H, `screenshot size ${png.w}x${png.h}`);
  need(d2.diff === 0, `screenshot != golden: ${d2.diff} px differ, first=${JSON.stringify(d2.first)}`);
  log(`on-screen screenshot vs golden: ${d2.diff === 0 ? "EXACT MATCH" : "MISMATCH"} (${d2.diff} differing px; ${png.w}x${png.h} から左上 ${W}x${H})`);

  // ---- 描画経路の実測 (worker: BGRA->RGBA 変換 + putImageData, 合成画像) ----
  const bench = {};
  for (const [bw, bh, it] of [[1280, 720, 30], [1920, 1080, 20]]) {
    const r = await E(`window.__e2e.host.bench(${bw}, ${bh}, ${it})`);
    bench[`${bw}x${bh}`] = { convertMs: +r.convertMs.toFixed(2), convertPutMs: +r.convertPutMs.toFixed(2), fps: +(1000 / r.convertPutMs).toFixed(1) };
  }
  log("renderer throughput (full-frame convert+putImageData, headless chrome, software canvas):", JSON.stringify(bench));
  fs.writeFileSync(path.join(OUTDIR, "bench.json"), JSON.stringify(bench, null, 1));

  // ---- 共有領域の統計 ----
  const st = await E(`(() => { const v = window.__e2e.host.view; const g = (i) => Atomics.load(v.i32, i) >>> 0; return { inPushed: g(32), inDropped: g(33), inConsumed: g(34), outPushed: g(35), outFullWaits: g(36), presentSeq: g(37), presentDone: g(38), msgs: g(39), timers: g(40), paints: g(41), frames: window.__e2e.host.frames }; })()`);
  const memBytes = await E("window.__e2e.memory.buffer.byteLength");
  log("shared stats:", JSON.stringify(st), "wasm memory:", memBytes, "bytes");
  need(st.inDropped === 0, "input ring dropped events");
  need(st.presentDone === st.presentSeq, "present_done_seq != present_seq (renderer not caught up)");
  need(st.timers >= 3, "timer fires < 3");

  // ---- 終了: ESC -> DestroyWindow -> WM_DESTROY -> PostQuitMessage -> ExitProcess ----
  await drv.press("Escape");
  await L(`waitLog("app: destroy")`);
  const code = await E(`window.__e2e.host.exited`);
  need(code === 0, `exit code ${code}`);
  log("app exited via ExitProcess, code=" + code);
  if (process.env.E2E_MODE === "reach") {   // 到達 API ログ (CAB-156): ExitProcess で dump された GUI-REACH 行が host に届き内容が妥当であること
    const rl = await E("window.__e2e.host.logs.filter((l) => l.startsWith('GUI-REACH'))");
    const reached = new Map(rl.map((l) => l.split(" ")).filter((a) => a[0] === "GUI-REACH").map((a) => [a[2], { calls: +a[3], st: a[4], p: a[5] }]));
    const sum = rl.find((l) => l.startsWith("GUI-REACH-SUMMARY"));
    for (const n of ["RegisterClassA", "CreateWindowExA", "GetMessageA", "DispatchMessageA", "BeginPaint", "FillRect", "BitBlt", "SetTimer", "SetCapture", "ExitProcess"])
      need(reached.has(n), `reach log lacks ${n}`);
    need(!!sum, "reach log lacks GUI-REACH-SUMMARY");
    need([...reached.values()].every((v) => v.st === "IMPL"), "reach log contains a STUB entry in a PASS run");
    need((reached.get("GetMessageA")?.calls ?? 0) >= 10, "GetMessageA calls < 10");
    log(`reach log OK: ${reached.size} distinct APIs (${sum}); first 6: ${[...reached.keys()].slice(0, 6).join(",")}`);
    fs.writeFileSync(path.join(OUTDIR, "reach.log"), rl.join("\n") + "\n");
  }
  const errs = await E("window.__e2e.errors");
  need(errs.length === 0, "page errors: " + JSON.stringify(errs));
  const perr = await drv.pageErrors();
  need(perr.length === 0, "driver page errors: " + JSON.stringify(perr));
  if (failures.length) console.log("[e2e] console:\n  " + (await drv.consoleMessages()).slice(-30).map((m) => m.text).join("\n  "));
}

main().then(async () => {
  clearTimeout(wd); await cleanup();
  if (failures.length) { console.error(`[e2e] FAILED (${failures.length})`); process.exit(1); }
  console.log("[e2e] PASS");
  process.exit(0);
}).catch(async (e) => { clearTimeout(wd); console.error("[e2e] ERROR", e); await cleanup(); process.exit(2); });
