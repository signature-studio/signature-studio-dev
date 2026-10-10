// E2E 対象サーバ起動。
//   preview  : vite preview (dist, vite.config.ts の server.headers で COOP/COEP)
//   dev      : vite dev server (HMR, プラグインで COOP/COEP)
//   edge-sim : 静的ファイルサーバ。R2 カスタムドメイン + Cloudflare Rules を
//              deploy/config/edge-policy.json から再現 (COOP/COEP/CORP/Cache-Control/
//              index rewrite/br 圧縮)。R2 同様 "/" の暗黙 index 解決は行わない。
import { spawn } from "node:child_process";
import { createReadStream, existsSync, mkdirSync, openSync, statSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import zlib from "node:zlib";
import {
  applyRequestRewrite,
  applyResponseHeaders,
  compressionAlgorithms,
  contentTypeFor,
  loadPolicy,
} from "../../../deploy/lib/policy.mjs";
import { freePort, waitHttp } from "./util.mjs";

export const E2E_DIR = path.resolve(import.meta.dirname, "..");
export const REPO_ROOT = path.resolve(E2E_DIR, "../..");
export const DIST = path.join(E2E_DIR, "work/dist");
const VITE = path.join(REPO_ROOT, "node_modules/.bin/vite");

function spawnVite(args, logName) {
  const logDir = path.join(E2E_DIR, "work/logs");
  mkdirSync(logDir, { recursive: true });
  const fd = openSync(path.join(logDir, `${logName}.log`), "w");
  return spawn(VITE, args, {
    cwd: REPO_ROOT,
    stdio: ["ignore", fd, fd],
    detached: true,
  });
}

function killTree(child) {
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    /* 既に終了 */
  }
}

async function startVite(kind) {
  const port = await freePort();
  const base = ["--port", String(port), "--strictPort", "--host", "127.0.0.1"];
  const args =
    kind === "preview" ? ["preview", "--outDir", DIST, ...base] : base;
  const child = spawnVite(args, kind);
  const url = `http://127.0.0.1:${port}`;
  await waitHttp(`${url}/`);
  return { url, stop: async () => killTree(child) };
}

function startEdgeSim() {
  const policy = loadPolicy();
  const server = http.createServer((req, res) => {
    const u = new URL(req.url, "http://edge-sim");
    let p = decodeURIComponent(u.pathname);
    p = applyRequestRewrite(policy, p);
    const file = path.join(DIST, p);
    const inDist = file.startsWith(DIST + path.sep);
    let st = null;
    try {
      st = inDist ? statSync(file) : null;
    } catch {
      /* 404 */
    }
    const ok = st?.isFile();
    const status = ok ? 200 : 404;
    const headers = applyResponseHeaders(policy, { path: p, status }, {});
    if (!ok) {
      res.writeHead(404, { ...headers, "Content-Type": "text/plain" });
      res.end("Not Found (edge-sim: R2 には暗黙 index/SPA fallback は無い)");
      return;
    }
    headers["Content-Type"] = contentTypeFor(policy, p);
    headers["ETag"] = `"${st.size.toString(16)}-${st.mtimeMs.toString(16)}"`;
    headers["Vary"] = "Accept-Encoding";
    if (req.headers["if-none-match"] === headers["ETag"]) {
      res.writeHead(304, headers);
      res.end();
      return;
    }
    const algos = compressionAlgorithms(policy, p);
    const ae = String(req.headers["accept-encoding"] ?? "");
    const enc = algos?.find(
      (a) => (a === "brotli" && /\bbr\b/.test(ae)) || (a === "gzip" && /\bgzip\b/.test(ae)),
    );
    if (req.method === "HEAD") {
      res.writeHead(200, headers);
      res.end();
      return;
    }
    if (enc) {
      headers["Content-Encoding"] = enc === "brotli" ? "br" : "gzip";
      res.writeHead(200, headers);
      const c =
        enc === "brotli"
          ? zlib.createBrotliCompress({ params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 5 } })
          : zlib.createGzip();
      createReadStream(file).pipe(c).pipe(res);
    } else {
      headers["Content-Length"] = st.size;
      res.writeHead(200, headers);
      createReadStream(file).pipe(res);
    }
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      resolve({
        url: `http://127.0.0.1:${port}`,
        stop: async () => {
          server.closeAllConnections();
          server.close();
        },
      });
    });
  });
}

export async function startTarget(name) {
  if (!existsSync(DIST) && name !== "dev") {
    throw new Error(`dist が無い: ${DIST} (run.sh がビルドする)`);
  }
  if (name === "preview" || name === "dev") return startVite(name);
  if (name === "edge-sim") return startEdgeSim();
  throw new Error(`unknown target: ${name}`);
}
