import { createReadStream, existsSync, statSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";

const here = path.dirname(fileURLToPath(import.meta.url));

// crossOriginIsolated (SAB 用) を有効化する COOP/COEP ヘッダミドルウェア
function crossOriginIsolation(): Plugin {
  return {
    name: "coop-coep",
    configureServer(server) {
      server.middlewares.use((_req, res, next) => {
        res.setHeader("Cross-Origin-Opener-Policy", "same-origin");
        res.setHeader("Cross-Origin-Embedder-Policy", "require-corp");
        next();
      });
    },
  };
}

/**
 * `/wasm/*` を tools/runtime/work/wasm (stage_wasm.mjs が生成) から配信する (dev / preview 共通)。
 * 本番は R2 バケット直配を想定 (同じ URL 形・ハッシュ入りファイル名 = immutable)。
 * Range 対応・content-length 付き (進捗 UI 用)。RUNTIME_WASM_DIR で配信元を差し替え可能。
 */
function wasmAssets(): Plugin {
  const dir = process.env.RUNTIME_WASM_DIR ?? path.join(here, "tools/runtime/work/wasm");
  const mw = (req: IncomingMessage, res: ServerResponse, next: () => void): void => {
    const url = new URL(req.url ?? "/", "http://x");
    if (!url.pathname.startsWith("/wasm/")) return next();
    const rel = decodeURIComponent(url.pathname.slice("/wasm/".length));
    const file = path.join(dir, rel);
    if (!file.startsWith(dir) || !existsSync(file) || !statSync(file).isFile()) {
      res.statusCode = 404;
      res.end("not found");
      return;
    }
    const isWasm = file.endsWith(".wasm");
    const isGlue = file.endsWith(".mjs");
    // glue (.mjs) は pthread Worker のスクリプトとしても読まれる。COEP: require-corp 下の Worker script は
    // 応答自身に COEP が無いとロードに失敗する (preview ではこのミドルウェアが preview.headers より先に走るため明示する)
    res.setHeader("Cross-Origin-Opener-Policy", "same-origin");
    res.setHeader("Cross-Origin-Embedder-Policy", "require-corp");
    res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
    res.setHeader("Content-Type", isWasm ? "application/wasm" : isGlue ? "text/javascript" : "application/json");
    res.setHeader("Cache-Control", isWasm || isGlue ? "public, max-age=31536000, immutable" : "no-cache");
    // 事前圧縮 (`<file>.br`, stage_wasm.mjs が生成) があり Accept-Encoding: br なら Content-Encoding: br で返す (本番 R2 配信と同形)
    const br = `${file}.br`;
    if ((isWasm || isGlue) && existsSync(br) && /\bbr\b/.test(String(req.headers["accept-encoding"] ?? ""))) {
      const bst = statSync(br);
      res.setHeader("Content-Encoding", "br");
      res.setHeader("Vary", "Accept-Encoding");
      res.setHeader("Content-Length", bst.size);
      createReadStream(br).pipe(res);
      return;
    }
    const st = statSync(file);
    res.setHeader("Accept-Ranges", "bytes");
    const m = /bytes=(\d+)-(\d*)/.exec(String(req.headers.range ?? ""));
    if (m) {
      const s = Number(m[1]);
      const e = m[2] ? Number(m[2]) : st.size - 1;
      res.statusCode = 206;
      res.setHeader("Content-Range", `bytes ${s}-${e}/${st.size}`);
      res.setHeader("Content-Length", e - s + 1);
      createReadStream(file, { start: s, end: e }).pipe(res);
    } else {
      res.setHeader("Content-Length", st.size);
      createReadStream(file).pipe(res);
    }
  };
  return {
    name: "runtime-wasm-assets",
    configureServer(server) {
      server.middlewares.use(mw);
    },
    configurePreviewServer(server) {
      server.middlewares.use(mw);
    },
  };
}

export default defineConfig({
  plugins: [crossOriginIsolation(), wasmAssets()],
  server: {
    // tools/ 配下は巨大な work/ を多数抱える (inotify watch 枯渇 ENOSPC の原因)。HMR 対象外にする
    watch: { ignored: ["**/tools/**", "**/deploy/**", "**/dist/**", "**/node_modules/**"] },
    // COOP/COEP 検証 (preview サーバにも同じヘッダを付けないと SAB が無効になる)
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
    },
  },
  preview: {
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
    },
  },
  worker: {
    format: "es",
  },
  build: {
    target: "es2022",
  },
});
