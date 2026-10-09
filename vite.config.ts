import { defineConfig, type Plugin } from "vite";

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

export default defineConfig({
  plugins: [crossOriginIsolation()],
  server: {
    // COOP/COEP 検証 (preview サーバにも同じヘッダを付けないと SAB が無効になる)
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
    },
  },
  build: {
    target: "es2022",
  },
});
