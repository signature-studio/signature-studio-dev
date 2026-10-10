// COOP/COEP 付き最小静的サーバ (probe / bench 用)。Range 対応・任意ヘッダ追加。
import http from "node:http";
import { createReadStream, statSync, existsSync } from "node:fs";
import path from "node:path";

const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript",
  ".wasm": "application/wasm", ".json": "application/json", ".css": "text/css" };

/** mounts: [{prefix:'/', dir:'/abs'}] 先頭から最長一致。 opts.headers: 追加レスポンスヘッダ。 */
export function serve(mounts, { port = 0, headers = {}, isolate = true, onRequest } = {}) {
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, "http://x");
    onRequest?.(req, u);
    let file = null;
    for (const m of mounts) {
      if (u.pathname.startsWith(m.prefix)) {
        const rel = decodeURIComponent(u.pathname.slice(m.prefix.length));
        const cand = path.join(m.dir, rel);
        if (cand.startsWith(m.dir) && existsSync(cand) && statSync(cand).isFile()) { file = cand; break; }
      }
    }
    if (!file) { res.writeHead(404); res.end("not found"); return; }
    const st = statSync(file);
    const h = { "Content-Type": MIME[path.extname(file)] || "application/octet-stream", "Accept-Ranges": "bytes", ...headers };
    if (isolate) {
      h["Cross-Origin-Opener-Policy"] = "same-origin";
      h["Cross-Origin-Embedder-Policy"] = "require-corp";
      h["Cross-Origin-Resource-Policy"] = "same-origin";
    }
    const range = req.headers.range?.match(/bytes=(\d+)-(\d*)/);
    if (range) {
      const s = +range[1], e = range[2] ? +range[2] : st.size - 1;
      res.writeHead(206, { ...h, "Content-Range": `bytes ${s}-${e}/${st.size}`, "Content-Length": e - s + 1 });
      createReadStream(file, { start: s, end: e }).pipe(res);
    } else {
      res.writeHead(200, { ...h, "Content-Length": st.size });
      createReadStream(file).pipe(res);
    }
  });
  return new Promise((r) => srv.listen(port, "127.0.0.1", () => r({ srv, port: srv.address().port, close: () => new Promise((rr) => { srv.closeAllConnections?.(); srv.close(rr); }) })));
}
