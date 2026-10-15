// PY-108 (#2918): 静的版の subinterp 反復で wasm 線形メモリの増加を headless Chrome で測る driver
//   (static64_browser_probe.mjs と同じ配信・Chrome 起動)。
//   node tests/static64_growth_probe.mjs <wasm> <mode 0|2> <n> <python code>  -> "STATIC64 GROWTH {json}" / exit 0|1
//   前提: build_flpy_static.sh 済み (dist/<wasm>.*)。本体: tests/browser/static64_growth.mjs
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";

const [name = "flpy_static64", mode = "0", n = "160", code = "result = '1'"] = process.argv.slice(2);
const here = path.dirname(new URL(import.meta.url).pathname);
const server = spawn(process.execPath, [path.join(here, "browser/serve.mjs"), "0"], { stdio: ["ignore", "pipe", "inherit"] });
const port = await new Promise((res) => server.stdout.on("data", (d) => { const m = /PORT (\d+)/.exec(String(d)); if (m) res(m[1]); }));
const prof = fs.mkdtempSync(path.join(os.tmpdir(), "flpy-static64-growth-chrome-"));
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
const t0 = Date.now();
const qs = new URLSearchParams({ static: name, mode, n, code }).toString();
await send("Page.navigate", { url: `http://127.0.0.1:${port}/tests/browser/static64_growth.html?${qs}` });
let text = "PENDING";
for (let i = 0; i < 900 && !/^RESULT /.test(text); i++) {
  await new Promise((r) => setTimeout(r, 200));
  const r = await send("Runtime.evaluate", { expression: "document.getElementById('result')?.textContent", returnByValue: true });
  text = r.result?.result?.value ?? "PENDING";
}
const wall_ms = Date.now() - t0;
ws.close(); chrome.kill(); server.kill();
const m = /^RESULT (.*)$/s.exec(text);
const out = m ? JSON.parse(m[1]) : { ok: false, pending: true, progress: text, logs };
if (!out.ok) out.logs = logs;
out.wall_ms = wall_ms;
console.log("STATIC64 GROWTH " + (out.ok ? "OK " : "FAIL ") + JSON.stringify(out));
process.exit(out.ok ? 0 : 1);
