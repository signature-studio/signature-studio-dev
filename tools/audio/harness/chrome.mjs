// headless Chrome 駆動 (CDP 直叩き, 依存なし) + COOP/COEP 付き静的サーバ。
// 使い方 (ライブラリ): import { withChrome } from "./chrome.mjs"
//   await withChrome({ root, page }, async (cdp) => { await cdp.eval("..."); })
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawn } from "node:child_process";

const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8", ".wasm": "application/wasm",
  ".json": "application/json", ".map": "application/json",
};

export function serve(root) {
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, "http://x");
    let p = path.join(root, decodeURIComponent(u.pathname));
    if (!p.startsWith(root)) { res.writeHead(403); return res.end(); }
    if (fs.existsSync(p) && fs.statSync(p).isDirectory()) p = path.join(p, "index.html");
    if (!fs.existsSync(p)) { res.writeHead(404); return res.end("404 " + u.pathname); }
    res.writeHead(200, {
      "Content-Type": MIME[path.extname(p)] ?? "application/octet-stream",
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
      "Cross-Origin-Resource-Policy": "same-origin",
      "Cache-Control": "no-store",
    });
    fs.createReadStream(p).pipe(res);
  });
  return new Promise((ok) => srv.listen(0, "127.0.0.1", () => ok({ srv, port: srv.address().port })));
}

export async function withChrome({ root, page, flags = [], log = () => {} }, fn) {
  const { srv, port } = await serve(root);
  const udd = fs.mkdtempSync(path.join(fs.existsSync("/tmp/opencode") ? "/tmp/opencode" : os.tmpdir(), "flaudio-chrome-"));
  const args = [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--remote-debugging-port=0",
    `--user-data-dir=${udd}`,
    "--autoplay-policy=no-user-gesture-required",
    "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
    "--no-first-run", "--no-default-browser-check", ...flags, "about:blank",
  ];
  const cp = spawn(process.env.CHROME ?? "google-chrome", args, { stdio: ["ignore", "ignore", "pipe"] });
  let errbuf = "";
  cp.stderr.on("data", (d) => (errbuf += d));
  try {
    // DevToolsActivePort が出るまで待つ (fs.watch でイベント待ち)
    const portFile = path.join(udd, "DevToolsActivePort");
    await new Promise((ok, ng) => {
      const t = setTimeout(() => ng(new Error("chrome 起動タイムアウト\n" + errbuf)), 30000);
      const check = () => { if (fs.existsSync(portFile) && fs.readFileSync(portFile, "utf8").includes("\n")) { clearTimeout(t); w.close(); ok(); } };
      const w = fs.watch(udd, check);
      cp.on("exit", (c) => ng(new Error("chrome exit " + c + "\n" + errbuf)));
      check();
    });
    const [dport] = fs.readFileSync(portFile, "utf8").split("\n");
    const targets = await (await fetch(`http://127.0.0.1:${dport}/json/list`)).json();
    const tgt = targets.find((t) => t.type === "page");
    const ws = new WebSocket(tgt.webSocketDebuggerUrl);
    await new Promise((ok, ng) => { ws.onopen = ok; ws.onerror = ng; });
    let id = 0; const pend = new Map(); const events = [];
    ws.onmessage = (m) => {
      const d = JSON.parse(m.data);
      if (d.id && pend.has(d.id)) { const { ok, ng } = pend.get(d.id); pend.delete(d.id); d.error ? ng(new Error(JSON.stringify(d.error))) : ok(d.result); }
      else if (d.method === "Runtime.consoleAPICalled") {
        const txt = d.params.args.map((a) => a.value ?? a.description ?? "").join(" ");
        log(`[console.${d.params.type}] ${txt}`);
      } else if (d.method === "Runtime.exceptionThrown") {
        log(`[exception] ${JSON.stringify(d.params.exceptionDetails.exception?.description ?? d.params.exceptionDetails.text)}`);
      } else events.push(d);
    };
    const send = (method, params = {}) => new Promise((ok, ng) => { const i = ++id; pend.set(i, { ok, ng }); ws.send(JSON.stringify({ id: i, method, params })); });
    await send("Runtime.enable"); await send("Page.enable");
    const navigate = async (pg) => {
      await send("Page.navigate", { url: `http://127.0.0.1:${port}/${pg}` });
      await new Promise((ok) => { const iv = setInterval(async () => { try { const r = await send("Runtime.evaluate", { expression: "document.readyState + '|' + location.pathname" }); if (r.result.value.startsWith("complete")) { clearInterval(iv); ok(); } } catch { /* ナビゲーション中 */ } }, 200); });
    };
    await navigate(page);
    const cdp = {
      send, navigate,
      async eval(expression) {
        const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true, userGesture: true });
        if (r.exceptionDetails) throw new Error("page exception: " + JSON.stringify(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text));
        return r.result.value;
      },
    };
    return await fn(cdp);
  } finally {
    cp.kill("SIGKILL");
    srv.close();
    fs.rmSync(udd, { recursive: true, force: true });
  }
}
