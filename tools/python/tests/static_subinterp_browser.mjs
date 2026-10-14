// PY-109 (#2919): headless Chrome 上で静的版 (flpy_static64 = Memory64) の subinterp 12 check を実行する。
//   node 22 は table64 を検証できないため node 版 (static_subinterp_probe.mjs) は使えない。check 名・判定は同じ。
//   node tests/static_subinterp_browser.mjs [--neg]   環境変数: STATIC_WASM (既定 flpy_static64)・STATIC_MEM64 (既定 1)
//   PASS: "STATIC SUBINTERP OK {...}" exit 0 / FAIL: exit 2 / --neg: 期待を 1 つ壊し、その check だけが FAIL したとき "STATIC SUBINTERP NEG-CONTROL DETECTED" exit 1
//   前提: build_cpython_wasm64.sh → FLPY_MEMORY64=1 CPY_BUILD=$PWD/work/build-wasm64 STATIC_OUT=flpy_static64 bash build_flpy_static.sh 済み
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const NAME = process.env.STATIC_WASM || "flpy_static64";
const MEM64 = process.env.STATIC_MEM64 || "1";
const neg = process.argv.includes("--neg");
const server = spawn(process.execPath, [path.join(here, "browser/serve.mjs"), "0"], { stdio: ["ignore", "pipe", "inherit"] });
const port = await new Promise((res) => server.stdout.on("data", (d) => { const m = /PORT (\d+)/.exec(String(d)); if (m) res(m[1]); }));
const prof = fs.mkdtempSync(path.join(os.tmpdir(), "flpy-static64-chrome-"));
const chrome = spawn("google-chrome", ["--headless=new", "--no-sandbox", "--disable-gpu", `--user-data-dir=${prof}`, "--remote-debugging-port=0", "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
const wsUrl = await new Promise((res) => chrome.stderr.on("data", (d) => { const m = /DevTools listening on (ws:\/\/\S+)/.exec(String(d)); if (m) res(m[1]); }));
const dbg = new URL(wsUrl);
const targets = await new Promise((res, rej) => http.get({ host: dbg.hostname, port: dbg.port, path: "/json/list" }, (r) => { let b = ""; r.on("data", (c) => (b += c)); r.on("end", () => res(JSON.parse(b))); }).on("error", rej));
const page = targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pend = new Map(); const logs = [];
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
  else if (m.method === "Runtime.exceptionThrown") logs.push(JSON.stringify(m.params).slice(0, 400));
  else if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") logs.push(JSON.stringify(m.params.args.map((a) => a.value ?? a.description)).slice(0, 400));
};
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send("Runtime.enable"); await send("Page.enable");
const load0 = os.loadavg()[0];
const t0 = Date.now();
await send("Page.navigate", { url: `http://127.0.0.1:${port}/tests/browser/static_subinterp.html?static=${NAME}&mem64=${MEM64}${neg ? "&neg=1" : ""}` });
let text = "PENDING";
for (let i = 0; i < 1500 && !/^RESULT /.test(text); i++) {
  await new Promise((r) => setTimeout(r, 200));
  const r = await send("Runtime.evaluate", { expression: "document.getElementById('result')?.textContent", returnByValue: true });
  text = r.result?.result?.value ?? "PENDING";
}
const wall_ms = Date.now() - t0;
const load1 = os.loadavg()[0];
ws.close(); chrome.kill(); server.kill();
const m = /^RESULT (.*)$/s.exec(text);
const out = m ? JSON.parse(m[1]) : { ok: false, pending: true, progress: text };
out.wall_ms = wall_ms;
out.load_1m = { before: load0, after: load1 };
out.logs = logs.slice(0, 20);
const ok = out.ok === true && !out.error;
const tag = ok ? (neg ? "STATIC SUBINTERP NEG-CONTROL DETECTED " : "STATIC SUBINTERP OK ") : "STATIC SUBINTERP FAIL ";
console.log(tag + JSON.stringify({ browser: true, static: NAME, mem64: Number(MEM64), ...out }));
process.exit(ok ? (neg ? 1 : 0) : 2);
