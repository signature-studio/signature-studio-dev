#!/usr/bin/env node
// input/e2e.mjs — GUI-6 (#182) の Chrome e2e: 実 CDP 入力 (Input.dispatchKeyEvent / imeSetComposition / insertText / dispatchTouchEvent / dispatchMouseEvent)
//   → gui.ts (GuiHost) → 入力リング → wasm shim → ゲストの WndProc → LOG "G6 ..." を検査。入力リング drop 0 を最後に確認。
//   RetDec / FL 不要 (ゲストは input_app.c を emcc で直接 wasm 化)。FAIL が 1 件でもあれば exit 1。
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { launchChrome } from "../../runtime/lib/chrome.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const GUI = path.join(HERE, "..");
const WASM = process.env.GUI_WASM_DIR ? path.resolve(process.env.GUI_WASM_DIR) : path.join(GUI, "build", "input_wasm");
const MIME = { ".js": "text/javascript", ".mjs": "text/javascript", ".html": "text/html", ".wasm": "application/wasm" };
let failures = 0;
const ck = (name, ok, detail = "") => { console.log(`${ok ? "OK  " : "FAIL"} ${name}${detail ? "  — " + detail : ""}`); if (!ok) failures++; };

const roots = [["/wasm/", WASM], ["/js/", process.env.GUI_JS_DIR ? path.resolve(process.env.GUI_JS_DIR) : path.join(GUI, "build", "js")], ["/input/", HERE]];
const srv = http.createServer((req, res) => {
  let url = decodeURIComponent((req.url || "/").split("?")[0]);
  if (url === "/") url = "/input/index.html";
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
const load0 = os.loadavg()[0], t00 = Date.now();
console.log(`[input-e2e] ${chrome.version} load=${load0.toFixed(2)} cpus=${os.cpus().length} node=${process.version}`);
const dog = setTimeout(() => { console.error("[input-e2e] WATCHDOG"); process.exit(3); }, 80000);
try {
  const page = await chrome.newPage();
  await page.send("Emulation.setDeviceMetricsOverride", { width: 480, height: 360, deviceScaleFactor: 1, mobile: false });
  await page.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await page.send("Page.bringToFront");
  await page.goto(`http://127.0.0.1:${port}/`);
  // 副作用が目的: window.__ready の完了時に __bootVal を仕掛ける (削除すると下の waitForExpr が timeout する)
  await page.waitForExpr("window.__ready && window.__ready.then ? (window.__bootDone ||= (window.__ready.then((v)=>{window.__bootVal=v;}), false)) || window.__bootVal : false", 30000).catch(() => null);
  const bootVal = await page.waitForExpr("window.__bootVal", 30000);
  ck("crossOriginIsolated + SAB wasm memory", bootVal.crossOriginIsolated === true && bootVal.sab === true);
  const logs = () => page.evaluate("window.__g6.host.logs.filter((l)=>l.startsWith('G6 '))", { awaitPromise: false });
  let cursor = 0;
  const waitLog = async (prefix, n = 1, timeout = 8000) => {
    const t0 = Date.now();
    for (;;) {
      const all = await logs();
      const hits = all.slice(cursor).filter((l) => l.startsWith(prefix));
      if (hits.length >= n) { cursor = all.length; return hits; }
      if (Date.now() - t0 > timeout) { cursor = all.length; return hits; }
      await new Promise((r) => setTimeout(r, 25));
    }
  };
  const ready = await waitLog("G6 READY");
  ck("guest started (READY, default layout US 0x04090409)", ready.length === 1 && /layout=4090409/.test(ready[0]), ready[0]);
  await page.evaluate("document.getElementById('screen').focus()", { awaitPromise: false });

  const key = async (code, key, vk, extra = {}) => {
    await page.send("Input.dispatchKeyEvent", { type: "rawKeyDown", code, key, windowsVirtualKeyCode: vk, ...extra });
    await page.send("Input.dispatchKeyEvent", { type: "keyUp", code, key, windowsVirtualKeyCode: vk, ...extra });
  };
  // ---- 1) キー: scancode が shim へ渡り、US 配列で ToUnicode ----
  await key("KeyZ", "z", 0x5a);
  let l = await waitLog("G6 KEYDOWN");
  ck("US: KeyZ -> vk=5a sc=2c uni='z'", l.length === 1 && /vk=5a sc=2c ext=0 uni=7a n=1/.test(l[0]), l[0]);
  await key("ArrowLeft", "ArrowLeft", 0x25);
  l = await waitLog("G6 KEYDOWN");
  ck("extended key: ArrowLeft -> vk=25 sc=4b ext=1", l.length === 1 && /vk=25 sc=4b ext=1/.test(l[0]), l[0]);

  // ---- 2) 配列切替 (host → GUI_IN_LAYOUT): DE の物理 KeyY = VK_Z ----
  await page.evaluate("window.__g6.host.setLayout(0x0407)", { awaitPromise: false });
  await key("KeyY", "z", 0x59);   // DE 配列ではこの物理キーが 'z'
  l = await waitLog("G6 KEYDOWN");
  ck("DE: physical KeyY (sc 0x15) -> vk=5a ('Z'), uni='z'", l.length === 1 && /vk=5a sc=15 ext=0 uni=7a/.test(l[0]), l[0]);
  await key("KeyZ", "y", 0x5a);   // 物理 KeyZ (sc 0x2c) は DE で 'y'
  l = await waitLog("G6 KEYDOWN");
  ck("DE: physical KeyZ (sc 0x2c) -> vk=59 ('Y'), uni='y'", l.length === 1 && /vk=59 sc=2c ext=0 uni=79/.test(l[0]), l[0]);
  await page.evaluate("window.__g6.host.setLayout(0x040c)", { awaitPromise: false });
  await key("KeyQ", "a", 0x51);   // AZERTY: 物理 KeyQ (sc 0x10) = 'a'
  l = await waitLog("G6 KEYDOWN");
  ck("FR: physical KeyQ (sc 0x10) -> vk=41 ('A'), uni='a'", l.length === 1 && /vk=41 sc=10 ext=0 uni=61/.test(l[0]), l[0]);
  await page.evaluate("window.__g6.host.setLayout(0x0409)", { awaitPromise: false });
  await key("KeyQ", "q", 0x51);
  l = await waitLog("G6 KEYDOWN");
  ck("US restored: KeyQ -> vk=51 sc=10 uni='q'", l.length === 1 && /vk=51 sc=10 ext=0 uni=71/.test(l[0]), l[0]);

  // ---- 3) IME: CDP の imeSetComposition / insertText → composition イベント → WM_IME_* ----
  await page.evaluate("window.__g6.host.ime.focus()", { awaitPromise: false });
  await page.send("Input.imeSetComposition", { text: "かんじ", selectionStart: 3, selectionEnd: 3 });
  const comp = await waitLog("G6 IME", 2);   // START + COMP (host は 2 件しか送らない)
  const compOk = comp.length >= 2 && comp[0] === "G6 IME START" && comp[1].startsWith("G6 IME COMP n=3 u=304b30933058");
  ck("IME: compositionstart/update → START + COMPOSITION(GCS_COMPSTR) 'かんじ'", compOk, comp.join(" | "));
  const charsBefore = (await logs()).filter((x) => x.startsWith("G6 CHAR")).length;
  await page.send("Input.insertText", { text: "漢字" });
  const fin = await waitLog("G6 IME", 3, 4000);   // COMP(n=2) + RESULT + END
  ck("IME: commit → COMPOSITION(GCS_RESULTSTR) '漢字' + END", fin.some((x) => x.startsWith("G6 IME RESULT n=2 u=6f225b57")) && fin.includes("G6 IME END"), fin.join(" | "));
  const wmChar = (await logs()).filter((x) => x.startsWith("G6 CHAR")).length - charsBefore;
  ck("IME: no WM_CHAR synthesized for composed text (WM_CHAR delta across the composition)", wmChar === 0, `WM_CHAR delta ${wmChar}`);
  await page.send("Input.imeSetComposition", { text: "あ", selectionStart: 1, selectionEnd: 1 });
  await waitLog("G6 IME", 2);   // START + COMP
  await page.send("Input.imeSetComposition", { text: "", selectionStart: 0, selectionEnd: 0 });   // 変換中文字列を空にして取消
  await page.evaluate("window.__g6.host.ime.dispatchEvent(new CompositionEvent('compositionend', { data: '' }))", { awaitPromise: false });   // ブラウザが end を出さない実装向けの保険 (二重 END は shim が無視)
  const canc = await waitLog("G6 IME", 2, 3000);   // COMP(n=0) + END
  const allImeAfter = (await logs()).slice(-4);
  ck("IME: cancel → exactly one END and no empty RESULT (duplicate cancel ignored by shim)", canc.filter((x) => x === "G6 IME END").length <= 1 && !allImeAfter.some((x) => x.startsWith("G6 IME RESULT n=0")) && (await logs()).filter((x) => x === "G6 IME END").length === 2, `ENDs total=${(await logs()).filter((x) => x === "G6 IME END").length} tail=${allImeAfter.join(" | ")}`);

  // ---- 4) タッチ: CDP dispatchTouchEvent → WM_TOUCH + 2 本指ズーム WM_GESTURE ----
  await page.evaluate("document.getElementById('screen').focus()", { awaitPromise: false });
  await page.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: 100, y: 100, id: 1 }] });
  let t = await waitLog("G6 TOUCH");
  ck("touch: touchStart → WM_TOUCH id/x/y/DOWN|PRIMARY (RegisterTouchWindow)", t.length === 1 && /x=100 y=100 fl=12/.test(t[0]), t[0]);
  await page.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: 100, y: 100, id: 1 }, { x: 160, y: 100, id: 2 }] });
  const z0 = await waitLog("G6 GESTURE");
  ck("two-finger → WM_GESTURE GID_ZOOM GF_BEGIN, distance 60", z0.length === 1 && /id=3 fl=1 arg=60/.test(z0[0]), z0[0]);
  await page.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: 100, y: 100, id: 1 }, { x: 190, y: 100, id: 2 }] });
  const z1 = await waitLog("G6 GESTURE");
  ck("pinch out → GID_ZOOM distance 90", z1.length === 1 && /id=3 fl=0 arg=90/.test(z1[0]), z1[0]);
  await page.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  const z2 = await waitLog("G6 GESTURE");
  ck("fingers lift → GF_END", z2.length >= 1 && /id=3 fl=4/.test(z2[0]), z2.join("|"));
  const tmouse = (await logs()).filter((x) => x.startsWith("G6 LBUTTON")).length;
  ck("registered window: touch is NOT promoted to mouse", tmouse === 0, `LBUTTON* count ${tmouse}`);

  // ---- 5) Pointer Lock: マウス押下 (SetCapture + ShowCursor(FALSE)) → host へ POINTER_LOCK 要求、ドラッグ中 cursor は相対量で動く ----
  const r0 = await page.evaluate("window.__g6.host.lockRequests", { awaitPromise: false });
  await page.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 160, y: 100 });
  await page.send("Input.dispatchMouseEvent", { type: "mousePressed", x: 160, y: 100, button: "left", buttons: 1, clickCount: 1 });
  await waitLog("G6 LBUTTONDOWN");
  const gotReq = await page.waitForExpr(`window.__g6.host.lockRequests > ${r0}`, 5000).catch(() => false);
  ck("mouse-down with hidden cursor + capture → host receives CMD_POINTER_LOCK request (requestPointerLock called)", !!gotReq, `lockRequests ${r0} → ${await page.evaluate("window.__g6.host.lockRequests", { awaitPromise: false })}`);
  // headless では実ロックが成立しない場合があるため、成立通知 (pointerlockchange) の経路は host の状態を直接ロック扱いにして movement 積算を検査する
  await page.evaluate("window.__g6.host.locked = true", { awaitPromise: false });
  await page.evaluate(`(() => { const c = document.getElementById('screen'); c.dispatchEvent(new PointerEvent('pointermove', { pointerId: 1, pointerType: 'mouse', clientX: 0, clientY: 0, movementX: 30, movementY: -20, buttons: 1, bubbles: true })); })()`, { awaitPromise: false });
  const dm = await waitLog("G6 DRAGMOVE");
  ck("locked: relative movement (+30,-20) accumulates onto the virtual cursor (160,100 → 190,80)", dm.length === 1 && /cur=190,80/.test(dm[0]) && /x=190 y=80/.test(dm[0]), dm[0]);
  await page.evaluate("window.__g6.host.locked = false", { awaitPromise: false });
  await page.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: 160, y: 100, button: "left", buttons: 0, clickCount: 1 });
  await waitLog("G6 LBUTTONUP");

  // ---- 6) 入力リング drop 0 ----
  const st = await page.evaluate("(() => { const v = window.__g6.host.view; return { pushed: v.u32[33 - 1], dropped: v.u32[33], consumed: v.u32[34] }; })()", { awaitPromise: false });
  const ta = await page.evaluate("window.__g6.host.canvas.style.touchAction", { awaitPromise: false });
  ck("touch-action: GUI canvas は常に none (PM 承認 2026-10-13)", ta === "none", `touchAction=${JSON.stringify(ta)}`);
  ck("input ring: drop 0, all pushed consumed", st.dropped === 0 && st.pushed === st.consumed, `in_pushed=${st.pushed} in_dropped=${st.dropped} in_consumed=${st.consumed}`);
  ck("no page errors", (await page.evaluate("window.__g6.errors.length", { awaitPromise: false })) === 0 && page.exceptions.length === 0, page.exceptions.join("|"));
} catch (e) {
  ck("e2e driver completed", false, String(e?.stack ?? e));
} finally {
  clearTimeout(dog);
  console.log(`[input-e2e] ${failures === 0 ? "ALL PASS" : failures + " FAIL"}  (${((Date.now() - t00) / 1000).toFixed(1)} s, load ${load0.toFixed(2)} → ${os.loadavg()[0].toFixed(2)})`);
  await chrome.close().catch(() => {});
  srv.close();
  process.exit(failures ? 1 : 0);
}
