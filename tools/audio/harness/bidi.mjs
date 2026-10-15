// headless Firefox 駆動 (WebDriver BiDi 直叩き, 依存なし) + COOP/COEP 付き静的サーバ (chrome.mjs の serve を共用)。
// withChrome (chrome.mjs) と同じ形の cdp ({ navigate, eval }) を返すので、ページ側の window.__done の取り方は同じ。
// 使い方: await withFirefox({ root, page }, async (ff) => { await ff.eval("window.__done"); })
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { serve } from "./chrome.mjs";

// chrome.mjs の --autoplay-policy=no-user-gesture-required / --use-fake-ui-for-media-stream 相当を profile の user.js で与える
const USER_JS = [
  'user_pref("media.autoplay.default", 0);',
  'user_pref("media.autoplay.blocking_policy", 0);',
  'user_pref("media.navigator.permission.disabled", true);',
  'user_pref("media.navigator.streams.fake", true);',
  'user_pref("browser.shell.checkDefaultBrowser", false);',
  'user_pref("browser.aboutwelcome.enabled", false);',
  'user_pref("datareporting.policy.dataSubmissionEnabled", false);',
  'user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);',
].join("\n") + "\n";

// FIREFOX 環境変数が無いときの実行ファイル (OS 別の既定インストール先)。Linux は PATH の firefox
const FIREFOX_BIN = { win32: "C:\\Program Files\\Mozilla Firefox\\firefox.exe", darwin: "/Applications/Firefox.app/Contents/MacOS/firefox" }[process.platform] ?? "firefox";

const freePort = () => new Promise((ok, ng) => {
  const s = net.createServer();
  s.on("error", ng);
  s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => ok(p)); });
});

export async function withFirefox({ root, page, flags = [], log = () => {} }, fn) {
  const { srv, port } = await serve(root);
  const prof = fs.mkdtempSync(path.join(os.tmpdir(), "flaudio-ff-"));
  fs.writeFileSync(path.join(prof, "user.js"), USER_JS);
  const bidiPort = await freePort();
  const args = ["--headless", "--no-remote", "--profile", prof, "--remote-debugging-port", String(bidiPort), ...flags, "about:blank"];
  const cp = spawn(process.env.FIREFOX ?? FIREFOX_BIN, args, { stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, MOZ_HEADLESS: "1" } });
  let errbuf = "";
  let onListen = () => {};
  const listening = new Promise((ok, ng) => {
    const t = setTimeout(() => ng(new Error("firefox BiDi 待受けタイムアウト\n" + errbuf.slice(-2000))), 60000);
    onListen = () => { clearTimeout(t); ok(); };
    cp.on("exit", (c) => { clearTimeout(t); ng(new Error("firefox exit " + c + "\n" + errbuf.slice(-2000))); });
  });
  const onData = (d) => {
    errbuf += d;
    if (/WebDriver BiDi listening on /.test(errbuf)) onListen();
  };
  cp.stdout.on("data", onData);
  cp.stderr.on("data", onData);
  let ws = null;
  try {
    await listening;
    ws = new WebSocket(`ws://127.0.0.1:${bidiPort}/session`);
    await new Promise((ok, ng) => { ws.onopen = ok; ws.onerror = () => ng(new Error("BiDi WebSocket 接続失敗")); });
    let id = 0; const pend = new Map();
    ws.onmessage = (m) => {
      const d = JSON.parse(m.data);
      if (d.type === "event") {
        if (d.method === "log.entryAdded") log(`[log.${d.params.level}] ${d.params.text}`);
        return;
      }
      const p = pend.get(d.id);
      if (!p) return;
      pend.delete(d.id);
      d.type === "error" ? p.ng(new Error(`${d.error}: ${d.message}`)) : p.ok(d.result);
    };
    const send = (method, params = {}) => new Promise((ok, ng) => { const i = ++id; pend.set(i, { ok, ng }); ws.send(JSON.stringify({ id: i, method, params })); });
    await send("session.new", { capabilities: {} });
    await send("session.subscribe", { events: ["log.entryAdded"] });
    const { contexts } = await send("browsingContext.getTree", {});
    const context = contexts[0].context;
    const navigate = (pg) => send("browsingContext.navigate", { context, url: `http://127.0.0.1:${port}/${pg}`, wait: "complete" });
    // 評価結果は JSON 文字列で返し、Node 側で parse する (BiDi の RemoteValue 直列化を避けて Runtime.evaluate の returnByValue と同じ値にする)
    const evaluate = async (expression) => {
      const r = await send("script.evaluate", {
        expression: `(async () => JSON.stringify(await (${expression})))()`, target: { context }, awaitPromise: true, resultOwnership: "none",
      });
      if (r.exceptionDetails) throw new Error("page exception: " + (r.exceptionDetails.text ?? JSON.stringify(r.exceptionDetails)));
      return r.result.type === "string" ? JSON.parse(r.result.value) : undefined;
    };
    await navigate(page);
    return await fn({ send, navigate, eval: evaluate });
  } finally {
    try { ws?.close(); } catch { /* 接続済みでなければ無視 */ }
    cp.kill("SIGKILL");
    srv.close();
    try { fs.rmSync(prof, { recursive: true, force: true, maxRetries: 20, retryDelay: 250 }); } catch { /* SIGKILL 直後の子プロセスとの書込み競合。結果を失わないよう握り潰す */ }
  }
}
