// 05-stage 出力 (site) を edge-policy 準拠で配信し、manifest の全ファイルを fetch して検査する。
//   node serve-check.mjs <site-dir> <deploy-manifest.json> [--serve]   (--serve: 検査せず URL を 1 行出して配信し続ける。tools/e2e/run.sh --url 用)
// 検査: 全 path が 200 / sha256 一致 / Content-Type が manifest.contentType と一致 / immutable 配下は 1 年 immutable /
//       .wasm は fetch -> WebAssembly.instantiateStreaming が通る (Node は MIME application/wasm 以外を TypeError で拒否する)。
import { createHash } from "node:crypto";
import { createReadStream, readFileSync, statSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { applyResponseHeaders, loadPolicy } from "../../../deploy/lib/policy.mjs";

const argv = process.argv.slice(2);
const serveOnly = argv.includes("--serve");
const [site, mf] = argv.filter((a) => !a.startsWith("--")).map((p) => path.resolve(p));
const manifest = JSON.parse(readFileSync(mf, "utf8"));
const policy = loadPolicy();
const server = http.createServer((req, res) => {
  const reqPath = decodeURIComponent(new URL(req.url, "http://x").pathname);
  const p = reqPath === "/" ? "/index.html" : reqPath; // Static Assets は / を index.html に解決する
  const file = path.join(site, p);
  let st;
  try { st = file.startsWith(site + path.sep) ? statSync(file) : null; } catch { st = null; }
  const headers = applyResponseHeaders(policy, { path: reqPath, status: st?.isFile() ? 200 : 404 }, {});
  if (!st?.isFile()) { res.writeHead(404, headers); res.end(); return; }
  const ext = p.split(".").pop();
  headers["Content-Type"] = policy.contentTypes[ext] ?? policy.defaultContentType;
  headers["Content-Length"] = st.size;
  res.writeHead(200, headers);
  createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;
if (serveOnly) { console.log(base); await new Promise(() => {}); }
const errors = [];
let wasmOk = 0;
for (const f of manifest.files) {
  const r = await fetch(`${base}/${f.path}`);
  const buf = Buffer.from(await r.arrayBuffer());
  if (r.status !== 200) { errors.push(`${f.path}: HTTP ${r.status}`); continue; }
  if (createHash("sha256").update(buf).digest("hex") !== f.sha256) errors.push(`${f.path}: sha256 不一致`);
  const ct = r.headers.get("content-type");
  if (ct !== f.contentType) errors.push(`${f.path}: Content-Type ${ct} != ${f.contentType}`);
  if (/^(assets|wasm|data)\//.test(f.path) && f.path !== "wasm/manifest.json" && r.headers.get("cache-control") !== "public, max-age=31536000, immutable") {
    errors.push(`${f.path}: Cache-Control ${r.headers.get("cache-control")}`);
  }
  if (f.path.endsWith(".wasm")) {
    try {
      const res2 = await fetch(`${base}/${f.path}`);
      if (res2.headers.get("content-type") !== "application/wasm") throw new Error(`MIME ${res2.headers.get("content-type")}`);
      const { module } = await WebAssembly.instantiateStreaming(res2, {});
      void module;
      wasmOk++;
    } catch (e) {
      errors.push(`${f.path}: instantiateStreaming 失敗: ${e.message}`);
    }
  }
}
server.close();
console.log(`serve-check: ${manifest.files.length} files fetched, wasm instantiateStreaming OK ${wasmOk} (MIME application/wasm)`);
if (errors.length) { console.error(errors.join("\n")); process.exit(2); }
