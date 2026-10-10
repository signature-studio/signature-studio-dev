// COOP/COEP 付き静的サーバ (SharedArrayBuffer 用)。node tests/browser/serve.mjs <port> -> tools/python をルートに配信
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const types = { ".html": "text/html", ".mjs": "text/javascript", ".js": "text/javascript", ".json": "application/json", ".wasm": "application/wasm", ".data": "application/octet-stream", ".py": "text/plain", ".pyc": "application/octet-stream" };
const srv = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split("?")[0]).replace(/^\/tests\/browser\/$/, "/tests/browser/index.html"));
  if (!p.startsWith(root) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end("nf"); }
  res.writeHead(200, {
    "content-type": types[path.extname(p)] || "application/octet-stream",
    "cross-origin-opener-policy": "same-origin", "cross-origin-embedder-policy": "require-corp", "cross-origin-resource-policy": "same-origin",
  });
  fs.createReadStream(p).pipe(res);
});
srv.listen(Number(process.argv[2] || 0), "127.0.0.1", () => console.log("PORT " + srv.address().port));
