#!/usr/bin/env node
// RT-3 GUI 結線 e2e (#121):
//   node tools/runtime/gui_e2e.mjs [--prod] [--neg] [--present=yield|blocking|both]
//   Vite (COOP/COEP) → headless Chrome → /?gui=selftest。CDP の実入力 (Input.dispatch*) → DOM → PumpInput → PumpRing.push →
//   fl-runtime Worker (MessagePump / waitAsync) → OffscreenCanvas(2D) → Page.captureScreenshot の画素で検証する。
//   同期は条件待ち (画素が期待値になるまで screenshot を polling)。固定 sleep なし。
import path from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";
import { createServer, build, preview } from "vite";
import { launchChrome } from "./lib/chrome.mjs";
import { decodePNG } from "./lib/png.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const args = new Map(process.argv.slice(2).map((a) => { const [k, v] = a.replace(/^--/, "").split("="); return [k, v ?? true]; }));
const modes = args.get("present") === "blocking" ? ["blocking"] : args.get("present") === "yield" ? ["yield"] : ["yield", "blocking"];
const W = 320, H = 200;

let vite, port;
if (args.has("prod")) {
  await build({ root, logLevel: "warn" });
  vite = await preview({ root, logLevel: "warn", preview: { port: 0, host: "127.0.0.1", strictPort: false } });
  port = vite.httpServer.address().port;
  vite.close = () => new Promise((r) => vite.httpServer.close(r));
} else {
  vite = await createServer({ root, logLevel: "warn", server: { port: 0, host: "127.0.0.1", strictPort: false } });
  await vite.listen();
  port = vite.httpServer.address().port;
}
const chrome = await launchChrome();
const results = [];
let exitCode = 0;
const ck = (name, ok, detail = "") => { results.push({ name, ok, detail }); console.log(`${ok ? "OK  " : "FAIL"} ${name}${detail ? "  — " + detail : ""}`); if (!ok) exitCode = 1; };
const near = (a, b, t = 12) => a.every((v, i) => Math.abs(v - b[i]) <= t);

async function run(mode) {
  const url = `http://127.0.0.1:${port}/?gui=selftest&present=${mode}&w=${W}&h=${H}${args.has("neg") ? "&neg=1" : ""}`;
  console.log(`\n[gui-e2e] present=${mode}  ${chrome.version}  ${url}`);
  const page = await chrome.newPage(url);
  const g = await page.waitForExpr("window.__gui && window.__gui.state !== 'booting' && ({state: window.__gui.state, error: window.__gui.error, coi: window.__gui.crossOriginIsolated})", 60000);
  ck(`[${mode}] crossOriginIsolated + GUI ready`, g.coi === true && g.state === "ready", g.error ?? g.state);
  if (g.state !== "ready") { await page.send("Page.close").catch(() => {}); return; }

  const shot = async () => decodePNG(Buffer.from((await page.send("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: W, height: H, scale: 1 } })).data, "base64"));
  /** 画素が期待色になるまで screenshot を polling (条件待ち)。成功時は経過 ms, 失敗は null */
  const waitPixel = async (x, y, rgb, timeoutMs = 4000) => {
    const t0 = performance.now();
    for (;;) {
      const s = await shot();
      if (near(s.px(x, y), rgb)) return Math.round(performance.now() - t0);
      if (performance.now() - t0 > timeoutMs) return null;
    }
  };
  const mouse = (type, x, y, extra = {}) => page.send("Input.dispatchMouseEvent", { type, x, y, button: "none", buttons: 0, ...extra });
  const key = async (code, vk, text) => {
    await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: text ?? code, code, text, windowsVirtualKeyCode: vk });
    await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: text ?? code, code, windowsVirtualKeyCode: vk });
  };

  const blocking = mode === "blocking";
  // 1) マウス移動 → 十字カーソル (横棒の端 (x+3, y) = 白)
  await mouse("mouseMoved", 100, 80);
  await mouse("mouseMoved", 150, 120);
  if (blocking) {
    // getMessage (Atomics.wait) で 1 タスクに居座る Worker は OffscreenCanvas が commit されない (Chrome 154 に OffscreenCanvas.commit() 無し)。
    // 入力は Worker に届いている (finish 後の集計で検査) が、画面には出ない = 仕様上の制約を e2e に固定する。
    const t = await waitPixel(153, 120, [255, 255, 255], 1500);
    ck("[blocking] (制約の固定) ブロック中の Worker 描画は画面へ commit されない", t === null, t === null ? "1500 ms 待っても画素は変化なし" : `想定外に ${t} ms で出現 → 制約が解消した可能性: 設計 (DESIGN §2) を見直す`);
  }
  if (!blocking) {
    const tMove = await waitPixel(153, 120, [255, 255, 255]);
    ck(`[${mode}] mouse move → OffscreenCanvas に十字カーソル (画素 (153,120)=白)`, tMove !== null, tMove === null ? "timeout (描画が screenshot に現れない)" : `${tMove} ms`);
  }
  if (!blocking) {
    // 2) 左ボタン押下 → 赤インジケータ (4..20, 4..20), 離す → 黒
    await mouse("mousePressed", 150, 120, { button: "left", buttons: 1, clickCount: 1 });
    const tDown = await waitPixel(12, 12, [255, 0, 0]);
    ck(`[${mode}] LBUTTONDOWN → 赤インジケータ`, tDown !== null, tDown === null ? "timeout" : `${tDown} ms`);
    await mouse("mouseReleased", 150, 120, { button: "left", buttons: 0, clickCount: 1 });
    const tUp = await waitPixel(12, 12, [0, 0, 0]);
    ck(`[${mode}] LBUTTONUP → インジケータ消灯`, tUp !== null, tUp === null ? "timeout" : `${tUp} ms`);
    // 3) 右ボタン → 緑
    await mouse("mousePressed", 150, 120, { button: "right", buttons: 2, clickCount: 1 });
    const tR = await waitPixel(32, 12, [0, 255, 0]);
    ck(`[${mode}] RBUTTONDOWN → 緑インジケータ`, tR !== null, tR === null ? "timeout" : `${tR} ms`);
    await mouse("mouseReleased", 150, 120, { button: "right", buttons: 0, clickCount: 1 });
    // 4) キー: A, B 押下 (keydown のみ保持 → 下端の白帯 8px)。keyUp は別途
    await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: "a", code: "KeyA", text: "a", windowsVirtualKeyCode: 65 });
    await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: "b", code: "KeyB", text: "b", windowsVirtualKeyCode: 66 });
    const tKey = await waitPixel(10, H - 8, [255, 255, 255]);
    ck(`[${mode}] KEYDOWN A,B → 下端の押下キー帯`, tKey !== null, tKey === null ? "timeout" : `${tKey} ms`);
    await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: "a", code: "KeyA", windowsVirtualKeyCode: 65 });
    await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: "b", code: "KeyB", windowsVirtualKeyCode: 66 });
    await key("KeyC", 67, "c");
  } else {
    // 入力は届いている (Worker 集計で検査) が画面には出ないので、画面系のチェックは行わず入力だけ流す
    await mouse("mousePressed", 150, 120, { button: "left", buttons: 1, clickCount: 1 });
    await mouse("mouseReleased", 150, 120, { button: "left", buttons: 0, clickCount: 1 });
    await mouse("mousePressed", 150, 120, { button: "right", buttons: 2, clickCount: 1 });
    await mouse("mouseReleased", 150, 120, { button: "right", buttons: 0, clickCount: 1 });
    await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: "a", code: "KeyA", text: "a", windowsVirtualKeyCode: 65 });
    await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: "b", code: "KeyB", text: "b", windowsVirtualKeyCode: 66 });
    await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: "a", code: "KeyA", windowsVirtualKeyCode: 65 });
    await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: "b", code: "KeyB", windowsVirtualKeyCode: 66 });
    await key("KeyC", 67, "c");
  }
  // 5) wheel
  await page.send("Input.dispatchMouseEvent", { type: "mouseWheel", x: 150, y: 120, deltaX: 0, deltaY: -100 });
  // 6) coalesce: 1 タスク内で 500 回の pointermove (合成イベント) → ring へは大幅に少ない件数
  const before = await page.evaluate("({...window.__gui.input})");
  await page.evaluate(`(() => { const c = document.getElementById('gui-canvas'); for (let i = 0; i < 500; i++) c.dispatchEvent(new PointerEvent('pointermove', { clientX: 40 + (i % 200), clientY: 60, buttons: 0, bubbles: true })); })()`);
  const tLast = blocking ? 0 : await waitPixel(40 + (499 % 200) + 3, 60, [255, 255, 255]);
  const after = await page.evaluate("({...window.__gui.input})");
  const seen = after.movesSeen - before.movesSeen, pushed = after.pushed - before.pushed;
  ck(`[${mode}] pointermove coalesce: 500 件 → ring へ ≤ 5 件、最終位置は反映${blocking ? " (blocking は Worker 集計で検査)" : ""}`, seen === 500 && pushed <= 5 && tLast !== null, `seen=${seen} pushed=${pushed} coalesced=${after.movesCoalesced - before.movesCoalesced} lastPixel=${tLast === null ? "timeout" : tLast + " ms"}`);

  // 7) 終了: Worker 側の受信集計を取得して突き合わせ
  const r = await page.evaluate("window.__gui.finish()");
  const has = (m) => r.byMessage[m] ?? 0;
  ck(`[${mode}] Worker 受信: MOUSEMOVE≥2 / L,R down+up / KEY A,B,C / CHAR 'c' / WHEEL`, has(0x200) >= 2 && has(0x201) === 1 && has(0x202) === 1 && has(0x204) === 1 && has(0x205) === 1 && has(0x100) >= 3 && r.chars.includes("c") && has(0x20a) === 1 && r.wheel === 120,
    `byMessage=${JSON.stringify(r.byMessage)} chars=${JSON.stringify(r.chars)} wheel=${r.wheel}`);
  ck(`[${mode}] ring: dropped 0 / rejected 0`, r.dropped === 0 && after.rejected === 0, `dropped=${r.dropped} rejected=${after.rejected}`);
  ck(`[${mode}] Worker 内 getImageData でも最終位置が描画済み`, r.pixelAtLastMove && near(r.pixelAtLastMove.slice(0, 3), [255, 255, 255], 2), JSON.stringify(r.pixelAtLastMove));
  ck(`[${mode}] blockedWaits (Atomics.wait / waitAsync) が発生 = ポーリングでない`, r.blockedWaits > 0, `waits=${r.blockedWaits}`);
  if (blocking) {
    const t = await waitPixel(139 + 3, 60, [255, 255, 255]);
    ck("[blocking] getMessage ループを抜けて 1 タスクが終わると描画が現れる (commit のタイミング問題であり経路は正常)", t !== null, t === null ? "timeout" : `${t} ms`);
  }
  await page.evaluate("window.__gui.terminate()");
  if (page.exceptions.length) ck(`[${mode}] page exceptions == 0`, false, page.exceptions[0].slice(0, 300));
  mkdirSync(path.join(here, "work"), { recursive: true });
  writeFileSync(path.join(here, `work/gui_e2e_${mode}.json`), JSON.stringify({ chrome: chrome.version, result: r, input: after }, null, 1));
}

/** gui_worker.ts → gui_renderer.ts 切り出しの回帰: 合成 GuiShared で GuiHost → render worker → OffscreenCanvas */
async function runRender() {
  const url = `http://127.0.0.1:${port}/?gui=render-selftest`;
  console.log(`\n[gui-e2e] render-selftest (GuiHost + gui_worker + 合成 GuiShared)  ${url}`);
  const page = await chrome.newPage(url);
  const r = await page.waitForExpr("window.__guiRender && window.__guiRender.state !== 'running' && window.__guiRender", 60000);
  ck("[render] GuiHost.attach → SURF_CREATE/PRESENT/FRAME_END → frame ack", r.state === "done" && r.frames >= 1, r.error ?? `frames=${r.frames}`);
  const exp = [240, 128, 16];
  ck("[render] readback: surface 画素 BGRA→RGBA 変換 (20,20)=(240,128,16)", Array.isArray(r.readbackPixel) && near(r.readbackPixel, exp, 0), JSON.stringify(r.readbackPixel));
  const shot = decodePNG(Buffer.from((await page.send("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: W, height: H, scale: 1 } })).data, "base64"));
  ck("[render] screenshot: surface 内 (20,20) と 外 (5,5)=黒", near(shot.px(20, 20), exp, 2) && near(shot.px(5, 5), [0, 0, 0], 0), `in=${shot.px(20, 20)} out=${shot.px(5, 5)}`);
  if (page.exceptions.length) ck("[render] page exceptions == 0", false, page.exceptions[0].slice(0, 300));
}

try {
  if (!args.has("neg")) await runRender();
  for (const m of modes) await run(m);
} catch (e) {
  console.error("[gui-e2e] FAILED:", e.stack || e);
  exitCode = 1;
} finally {
  await chrome.close();
  await vite.close();
}
console.log(exitCode === 0 ? "\n[gui-e2e] ALL OK" : "\n[gui-e2e] FAILED");
process.exit(exitCode);
