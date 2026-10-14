#!/usr/bin/env node
// AU-35 (#3193): safaridriver の代役 (WebDriver classic の最小応答)。Linux 上で harness/safari.mjs の HTTP 手順だけを確かめる用。
// 使い方: SAFARIDRIVER=tools/audio/test/safaridriver_mock.mjs node tools/audio/test/safari_mock_test.mjs
// ブラウザは動かさない。execute/async は script に "__fail" を含むとページ側の例外 (__exc・HTTP 200)、"__http" を含むと HTTP 500 (javascript error) を返し、それ以外は JSON 文字列を返す。
import http from "node:http";

const port = +process.argv[process.argv.indexOf("-p") + 1];
let nextSid = 1;
const sessions = new Map();
const send = (res, code, value) => { res.writeHead(code, { "content-type": "application/json" }); res.end(JSON.stringify({ value })); };
const body = (req) => new Promise((ok) => { let d = ""; req.on("data", (c) => (d += c)); req.on("end", () => ok(d ? JSON.parse(d) : {})); });

http.createServer(async (req, res) => {
  const b = await body(req);
  const p = req.url;
  if (req.method === "GET" && p === "/status") return send(res, 200, { ready: true });
  if (req.method === "POST" && p === "/session") {
    if (b.capabilities?.alwaysMatch?.browserName !== "Safari") return send(res, 400, { error: "session not created", message: "browserName" });
    const sid = "mock" + nextSid++;
    sessions.set(sid, { timeouts: null, urls: [] });
    return send(res, 200, { sessionId: sid, capabilities: { browserName: "Safari" } });
  }
  const m = p.match(/^\/session\/([^/]+)(\/.*)?$/);
  if (!m || !sessions.has(m[1])) return send(res, 404, { error: "invalid session id", message: p });
  const s = sessions.get(m[1]);
  const sub = m[2] ?? "";
  if (req.method === "DELETE" && sub === "") { sessions.delete(m[1]); return send(res, 200, null); }
  if (req.method === "POST" && sub === "/timeouts") { s.timeouts = b; return send(res, 200, null); }
  if (req.method === "POST" && sub === "/url") { s.urls.push(b.url); return send(res, 200, null); }
  if (req.method === "POST" && sub === "/execute/async") {
    if (!Array.isArray(b.args) || typeof b.script !== "string" || !b.script.includes("arguments[arguments.length - 1]")) return send(res, 400, { error: "invalid argument", message: "script" });
    if (b.script.includes("__fail")) return send(res, 200, { __exc: "Error: mock page exception" });
    if (b.script.includes("__http")) return send(res, 500, { error: "javascript error", message: "mock http error" });
    return send(res, 200, JSON.stringify({ ok: true, urls: s.urls, timeouts: s.timeouts }));
  }
  return send(res, 404, { error: "unknown command", message: p });
}).listen(port, "127.0.0.1");
