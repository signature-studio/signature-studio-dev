import { createReadStream, existsSync, statSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import { thirdPartyNotices } from "./tools/legal/notices/vite-plugin.mjs";

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

/**
 * `/py/*` を tools/python から配信する (dev / preview 共通。PY-4 #77)。
 * 許可リスト方式: host/ (ES module)・dist/ (flpy.js/wasm/data, build_flpy.sh 生成)・analysis/flapi/flapi_ids.json のみ。
 * work/ (利用者の FL 由来 MCPTools.pyc / midi.py / utils.py) は配信しない — 利用者が UI から供給する。
 * COEP: require-corp 下の module Worker script は応答側にも COEP/CORP が要る。
 */
function pyAssets(): Plugin {
  const dir = path.join(here, "tools/python");
  const allowed = /^(host\/[\w.-]+\.mjs|dist\/flpy\.(js|wasm|data)|analysis\/flapi\/flapi_ids\.json|analysis\/ilmcp\/(plugin_catalog|highlight_names)\.json)$/;
  const types: Record<string, string> = { ".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm", ".data": "application/octet-stream", ".json": "application/json" };
  const mw = (req: IncomingMessage, res: ServerResponse, next: () => void): void => {
    const url = new URL(req.url ?? "/", "http://x");
    if (!url.pathname.startsWith("/py/")) return next();
    const rel = decodeURIComponent(url.pathname.slice("/py/".length));
    const file = path.join(dir, rel);
    if (!allowed.test(rel) || !existsSync(file) || !statSync(file).isFile()) {
      res.statusCode = 404;
      res.end("not found");
      return;
    }
    res.setHeader("Cross-Origin-Opener-Policy", "same-origin");
    res.setHeader("Cross-Origin-Embedder-Policy", "require-corp");
    res.setHeader("Cross-Origin-Resource-Policy", "same-origin");
    res.setHeader("Content-Type", types[path.extname(file)] ?? "application/octet-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Content-Length", statSync(file).size);
    createReadStream(file).pipe(res);
  };
  return {
    name: "py-assets",
    configureServer(server) {
      server.middlewares.use(mw);
    },
    configurePreviewServer(server) {
      server.middlewares.use(mw);
    },
  };
}

/**
 * vreg wasm (`tools/startup/vreg/build.sh module` の生成物・gitignore) が無い checkout でも vite build を通す。
 * 無いときは `?license=import` の取込入口が読む createModule を「未生成」を投げるスタブに差し替え、build 時に警告を出す。
 * 生成物があれば実物を使う (製品 build・e2e_product_import とも同じ経路)。
 */
function vregWasmOptional(): Plugin {
  const SPEC = /\/vreg\/build\/vreg_wasm\.mjs$/;
  const STUB = "\0vreg-wasm-missing";
  return {
    name: "vreg-wasm-optional",
    enforce: "pre",
    resolveId(source, importer) {
      if (!importer || !SPEC.test(source)) return null;
      const abs = path.resolve(path.dirname(importer), source);
      if (existsSync(abs)) return null;
      this.warn(`vreg wasm 未生成 (${path.relative(here, abs)}): ?license=import は動かない。生成: bash tools/startup/vreg/build.sh module`);
      return STUB;
    },
    load(id) {
      return id === STUB
        ? 'export default async function createVregModule() { throw new Error("vreg wasm 未生成: bash tools/startup/vreg/build.sh module を実行してください"); }'
        : null;
    },
  };
}

export default defineConfig({
  plugins: [crossOriginIsolation(), wasmAssets(), pyAssets(), vregWasmOptional(), thirdPartyNotices()],
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
