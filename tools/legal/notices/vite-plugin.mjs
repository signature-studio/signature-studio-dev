// vite build で THIRD_PARTY_NOTICES.{txt,html} を成果物 (dist) に出す (LGL-3, #86)。
// FL 素材 (FL_WIN64_DIR) が無いと FL 同梱表記の本文が読めず「不完全」になる。不完全な NOTICES は
// deploy の stage ゲート (deploy/scripts/05-stage.mjs) が拒否する。NOTICES_STRICT=1 なら build 自体を失敗させる。
import { FL_WIN64_DIR } from "../../shared/paths.mjs";
import { generate, NOTICES_HTML, NOTICES_TXT } from "./lib.mjs";

export function thirdPartyNotices({ strict = process.env.NOTICES_STRICT === "1", flDir = FL_WIN64_DIR } = {}) {
  return {
    name: "third-party-notices",
    // dev では同じ URL で都度生成して返す (不完全でも警告のみ)。preview / 本番は build が出した成果物をそのまま配る
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = (req.url ?? "").split("?")[0];
        if (url !== `/${NOTICES_TXT}` && url !== `/${NOTICES_HTML}`) return next();
        const { txt, html } = generate({ flDir });
        const isTxt = url.endsWith(".txt");
        res.setHeader("Content-Type", `${isTxt ? "text/plain" : "text/html"}; charset=utf-8`);
        res.end(isTxt ? txt : html);
      });
    },
    generateBundle() {
      const { txt, html, model } = generate({ flDir, strict });
      if (!model.complete) this.warn(`THIRD_PARTY_NOTICES が不完全 (${model.missing.length} 件)。FL_WIN64_DIR を指定し NOTICES_STRICT=1 で再ビルドすること`);
      this.emitFile({ type: "asset", fileName: NOTICES_TXT, source: txt });
      this.emitFile({ type: "asset", fileName: NOTICES_HTML, source: html });
    },
  };
}
