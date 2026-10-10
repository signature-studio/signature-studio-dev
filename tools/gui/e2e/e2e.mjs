// e2e.mjs — headless Chrome E2E ドライバ (CDP; 追加依存なし / node >= 22)
//   lifted Win32 app (wasm, pthread) + gui shim + gui.ts/gui_worker.ts (OffscreenCanvas) を実ブラウザで動かし、
//   CDP の実入力イベント (Input.dispatchMouseEvent / dispatchKeyEvent) でシナリオを駆動、最終フレームを golden と比較する。
//   同期は全てイベント駆動 (LOG/フレーム ack の Promise)。固定 sleep なし。
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import zlib from "node:zlib";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, "..");
const BUILD = path.join(ROOT, "build");
const OUTDIR = path.join(BUILD, "e2e");
fs.mkdirSync(OUTDIR, { recursive: true });
const W = 320, H = 200;
const CHROME = process.env.CHROME || "google-chrome";
const WATCHDOG_MS = Number(process.env.E2E_TIMEOUT_MS || 90000);

const log = (...a) => console.log("[e2e]", ...a);
const failures = [];
const need = (c, m) => { if (!c) { failures.push(m); console.error("[e2e] FAIL:", m); } };

// ---------------- 静的サーバ (COOP/COEP) ----------------
const MIME = { ".js": "text/javascript", ".mjs": "text/javascript", ".html": "text/html", ".wasm": "application/wasm", ".ppm": "application/octet-stream", ".json": "application/json" };
function startServer() {
  const map = [["/wasm/", process.env.GUI_WASM_DIR ? path.resolve(process.env.GUI_WASM_DIR) : path.join(BUILD, "wasm")], ["/js/", path.join(BUILD, "js")], ["/e2e/", HERE], ["/golden/", path.join(ROOT, "golden")]];
  const srv = http.createServer((req, res) => {
    let url = decodeURIComponent((req.url || "/").split("?")[0]);
    if (url === "/") url = "/e2e/index.html";
    const hit = map.find(([p]) => url.startsWith(p));
    const headers = { "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp", "Cross-Origin-Resource-Policy": "same-origin", "Cache-Control": "no-store" };
    if (!hit) { res.writeHead(404, headers); res.end("not found"); return; }
    const file = path.join(hit[1], url.slice(hit[0].length));
    if (!file.startsWith(hit[1]) || !fs.existsSync(file)) { res.writeHead(404, headers); res.end("not found " + url); return; }
    res.writeHead(200, { ...headers, "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => srv.listen(0, "127.0.0.1", () => resolve({ srv, port: srv.address().port })));
}

// ---------------- 最小 CDP クライアント ----------------
class CDP {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.handlers = [];
    ws.addEventListener("message", (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id); this.pending.delete(m.id);
        m.error ? reject(new Error(`${m.error.message} ${m.error.data || ""}`)) : resolve(m.result);
      } else if (m.method) for (const h of this.handlers) h(m);
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  }
  on(h) { this.handlers.push(h); }
}

// ---------------- PNG (8bit RGB/RGBA, 非 interlace) デコード ----------------
function decodePNG(buf) {
  let p = 8, w = 0, h = 0, ct = 0; const idat = [];
  while (p < buf.length) {
    const len = buf.readUInt32BE(p), type = buf.toString("latin1", p + 4, p + 8), data = buf.subarray(p + 8, p + 8 + len);
    if (type === "IHDR") { w = data.readUInt32BE(0); h = data.readUInt32BE(4); ct = data[9]; if (data[8] !== 8 || data[12] !== 0) throw new Error("png: unsupported"); }
    if (type === "IDAT") idat.push(data);
    p += 12 + len;
  }
  const bpp = ct === 6 ? 4 : ct === 2 ? 3 : 0; if (!bpp) throw new Error("png: color type " + ct);
  const raw = zlib.inflateSync(Buffer.concat(idat)); const stride = w * bpp; const out = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)]; const line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? out[y * stride + x - bpp] : 0, b = y ? out[(y - 1) * stride + x] : 0, c = x >= bpp && y ? out[(y - 1) * stride + x - bpp] : 0;
      let v = line[x];
      if (f === 1) v += a; else if (f === 2) v += b; else if (f === 3) v += (a + b) >> 1;
      else if (f === 4) { const pp = a + b - c, pa = Math.abs(pp - a), pb = Math.abs(pp - b), pc = Math.abs(pp - c); v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
      out[y * stride + x] = v & 255;
    }
  }
  return { w, h, bpp, data: out };
}
function readPPM(file) {
  const b = fs.readFileSync(file); const m = /^P6\s+(\d+)\s+(\d+)\s+255\s/.exec(b.toString("latin1", 0, 32));
  return { w: +m[1], h: +m[2], data: b.subarray(m[0].length) };
}
function diffRGB(wantRGB, w, h, getPx) {
  let diff = 0, first = null;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const [r, g, b] = getPx(x, y), o = (y * w + x) * 3;
    if (r !== wantRGB[o] || g !== wantRGB[o + 1] || b !== wantRGB[o + 2]) { diff++; if (!first) first = { x, y, got: [r, g, b], want: [wantRGB[o], wantRGB[o + 1], wantRGB[o + 2]] }; }
  }
  return { diff, first };
}
function writePPM(file, w, h, getPx) {
  const out = Buffer.alloc(w * h * 3);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const [r, g, b] = getPx(x, y), o = (y * w + x) * 3; out[o] = r; out[o + 1] = g; out[o + 2] = b; }
  fs.writeFileSync(file, Buffer.concat([Buffer.from(`P6\n${w} ${h}\n255\n`), out]));
}

// ---------------- main ----------------
let chrome = null, srv = null;
const consoleLines = [];
const cleanup = () => { try { chrome?.kill("SIGKILL"); } catch {} try { srv?.close(); } catch {} };
const wd = setTimeout(() => { console.error("[e2e] WATCHDOG timeout; console tail:\n  " + consoleLines.slice(-40).join("\n  ")); cleanup(); process.exit(3); }, WATCHDOG_MS);

async function main() {
  const s = await startServer(); srv = s.srv;
  const url = `http://127.0.0.1:${s.port}/`;
  const udd = fs.mkdtempSync(path.join(process.env.OPENCODE_TMP || "/tmp/opencode", "gui-e2e-chrome-"));
  chrome = spawn(CHROME, ["--headless=new", "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0", `--user-data-dir=${udd}`,
    "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "--force-device-scale-factor=1", "--window-size=480,360", "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
  const wsUrl = await new Promise((resolve, reject) => {
    let acc = "";
    chrome.stderr.on("data", (d) => { acc += d; const m = /DevTools listening on (ws:\/\/\S+)/.exec(acc); if (m) resolve(m[1]); });
    chrome.on("exit", (c) => reject(new Error("chrome exited early code=" + c + "\n" + acc)));
  });
  const ws = new WebSocket(wsUrl); await new Promise((res, rej) => { ws.addEventListener("open", res); ws.addEventListener("error", rej); });
  const cdp = new CDP(ws);
  cdp.on((m) => {
    if (m.method === "Runtime.consoleAPICalled") consoleLines.push(m.params.args.map((a) => a.value ?? a.description).join(" "));
    if (m.method === "Runtime.exceptionThrown") consoleLines.push("EXC " + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
  });
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const S = (m, p) => cdp.send(m, p, sessionId);
  await S("Runtime.enable"); await S("Page.enable");
  await S("Emulation.setDeviceMetricsOverride", { width: 480, height: 360, deviceScaleFactor: 1, mobile: false });
  await S("Page.bringToFront");
  const E = async (expr) => {
    const r = await S("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error("eval failed: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text) + "\n  expr=" + expr);
    return r.result.value;
  };
  const loaded = new Promise((res) => cdp.on((m) => { if (m.method === "Page.loadEventFired") res(); }));
  await S("Page.navigate", { url });
  await loaded;
  const boot = await E("window.__ready");
  log("boot:", JSON.stringify(boot));
  need(boot.crossOriginIsolated === true, "crossOriginIsolated must be true (COOP/COEP)");
  need(boot.sab === true, "wasm memory must be SharedArrayBuffer");
  if (process.env.E2E_MODE === "failfast") {   // 未実装 API 到達 -> 即 abort + EXIT(0xFA11) が host に届くこと
    const code = await E("window.__e2e.host.exited");
    need(code === 0xFA11, `fail-fast exit code ${code} (want ${0xFA11})`);
    await E("new Promise((r) => setTimeout(r, 0))");
    need(consoleLines.some((l) => l.includes("FAIL-FAST: unimplemented Win32 API: Ellipse")), "console lacks FAIL-FAST message naming Ellipse");
    log(`fail-fast OK: host saw EXIT code 0x${code.toString(16)} and console named the API`);
    return;
  }
  const mouse = (type, x, y, extra = {}) => S("Input.dispatchMouseEvent", { type, x, y, button: "none", buttons: 0, ...extra });
  const L = (expr) => E(`window.__e2e.host.${expr}`);
  const syncPaint = (ev) => L(`waitLog("paint ev=${ev}")`);

  const t0 = Date.now();
  await L(`waitLog("app: created")`);
  await L(`waitLog("app: timer-done")`);
  log("app created + SetTimer x3 -> KillTimer ok");
  const click = async (x, y, ev) => {
    await mouse("mousePressed", x, y, { button: "left", buttons: 1, clickCount: 1 }); await syncPaint(ev);
    await mouse("mouseReleased", x, y, { button: "left", buttons: 0, clickCount: 1 }); await syncPaint(ev + 1);
  };
  await click(200, 150, 1);
  await click(210, 150, 3);
  await mouse("mousePressed", 30, 150, { button: "left", buttons: 1, clickCount: 1 }); await syncPaint(5);
  await mouse("mouseMoved", 100, 170, { button: "left", buttons: 1 }); await syncPaint(6);
  await mouse("mouseMoved", 150, 180, { button: "left", buttons: 1 }); await syncPaint(7);
  await mouse("mouseReleased", 150, 180, { button: "left", buttons: 0, clickCount: 1 }); await syncPaint(8);
  for (const [ch, code, vk, ev] of [["A", "KeyA", 65, 9], ["b", "KeyB", 66, 10]]) {
    await S("Input.dispatchKeyEvent", { type: "keyDown", key: ch, code, text: ch, windowsVirtualKeyCode: vk });
    await S("Input.dispatchKeyEvent", { type: "keyUp", key: ch, code, windowsVirtualKeyCode: vk });
    await syncPaint(ev);
  }
  log(`scenario complete in ${Date.now() - t0} ms`);

  // ---- 検証 1: OffscreenCanvas 読み戻し (worker) vs golden : exact ----
  const golden = readPPM(path.join(ROOT, "golden", "final.ppm"));
  const rb = await E(`(async () => { const r = await window.__e2e.host.readback(); let s = ""; const d = r.data; for (let i = 0; i < d.length; i += 0x8000) s += String.fromCharCode.apply(null, d.subarray(i, i + 0x8000)); return { w: r.width, h: r.height, b64: btoa(s) }; })()`);
  const rbuf = Buffer.from(rb.b64, "base64");
  const gotPx = (x, y) => { const o = (y * rb.w + x) * 4; return [rbuf[o], rbuf[o + 1], rbuf[o + 2]]; };
  const d1 = diffRGB(golden.data, W, H, gotPx);
  writePPM(path.join(OUTDIR, "canvas_readback.ppm"), W, H, gotPx);
  need(rb.w === W && rb.h === H, `readback size ${rb.w}x${rb.h}`);
  need(d1.diff === 0, `OffscreenCanvas readback != golden: ${d1.diff} px differ, first=${JSON.stringify(d1.first)}`);
  log(`OffscreenCanvas readback vs golden: ${d1.diff === 0 ? "EXACT MATCH" : "MISMATCH"} (${d1.diff} differing px of ${W * H})`);

  // ---- 検証 2: 実画面 (CDP スクリーンショット = ブラウザ合成後) vs golden ----
  const shot = await S("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: W, height: H, scale: 1 } });
  fs.writeFileSync(path.join(OUTDIR, "screenshot.png"), Buffer.from(shot.data, "base64"));
  const png = decodePNG(Buffer.from(shot.data, "base64"));
  const d2 = diffRGB(golden.data, W, H, (x, y) => { const o = (y * png.w + x) * png.bpp; return [png.data[o], png.data[o + 1], png.data[o + 2]]; });
  need(png.w === W && png.h === H, `screenshot size ${png.w}x${png.h}`);
  need(d2.diff === 0, `screenshot != golden: ${d2.diff} px differ, first=${JSON.stringify(d2.first)}`);
  log(`on-screen screenshot vs golden: ${d2.diff === 0 ? "EXACT MATCH" : "MISMATCH"} (${d2.diff} differing px)`);

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
  await S("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await S("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
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
  if (failures.length) console.log("[e2e] console:\n  " + consoleLines.slice(-30).join("\n  "));
}

main().then(() => {
  clearTimeout(wd); cleanup();
  if (failures.length) { console.error(`[e2e] FAILED (${failures.length})`); process.exit(1); }
  console.log("[e2e] PASS");
  process.exit(0);
}).catch((e) => { clearTimeout(wd); console.error("[e2e] ERROR", e); cleanup(); process.exit(2); });
