// headless Chrome を CDP で駆動し、module Worker + SAB 同期 RPC + wasm Python + MCPTools.pyc を実ブラウザで検証する。
//   node tests/browser_check.mjs   -> "BROWSER OK {...}" / exit 0
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";

const here = path.dirname(new URL(import.meta.url).pathname);
const server = spawn(process.execPath, [path.join(here, "browser/serve.mjs"), "0"], { stdio: ["ignore", "pipe", "inherit"] });
const port = await new Promise((res) => server.stdout.on("data", (d) => { const m = /PORT (\d+)/.exec(String(d)); if (m) res(m[1]); }));
const prof = fs.mkdtempSync(path.join(os.tmpdir(), "flpy-chrome-"));
const chrome = spawn("google-chrome", ["--headless=new", "--no-sandbox", "--disable-gpu", `--user-data-dir=${prof}`, "--remote-debugging-port=0", "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
const wsUrl = await new Promise((res) => chrome.stderr.on("data", (d) => { const m = /DevTools listening on (ws:\/\/\S+)/.exec(String(d)); if (m) res(m[1]); }));
const dbg = new URL(wsUrl);
const targets = await new Promise((res, rej) => http.get({ host: dbg.hostname, port: dbg.port, path: "/json/list" }, (r) => { let b = ""; r.on("data", (c) => (b += c)); r.on("end", () => res(JSON.parse(b))); }).on("error", rej));
const page = targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pend = new Map(); const logs = [];
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } else if (m.method === "Runtime.exceptionThrown" || m.method === "Runtime.consoleAPICalled") logs.push(JSON.stringify(m.params).slice(0, 400)); };
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send("Runtime.enable"); await send("Page.enable");
await send("Page.navigate", { url: `http://127.0.0.1:${port}/tests/browser/` });
let text = "PENDING";
for (let i = 0; i < 300 && text === "PENDING"; i++) {
  await new Promise((r) => setTimeout(r, 200));
  const r = await send("Runtime.evaluate", { expression: "document.getElementById('result')?.textContent", returnByValue: true });
  text = r.result?.result?.value ?? "PENDING";
}
ws.close(); chrome.kill(); server.kill();
const m = /^RESULT (.*)$/s.exec(text);
const out = m ? JSON.parse(m[1]) : { ok: false, pending: true, logs };
console.log((out.ok ? "BROWSER OK " : "BROWSER FAIL ") + JSON.stringify(out));
process.exit(out.ok ? 0 : 1);
