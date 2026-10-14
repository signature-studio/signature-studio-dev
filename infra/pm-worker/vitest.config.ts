import { defineConfig } from "vitest/config";
import { cloudflareTest } from "@cloudflare/vitest-plugin";

// 実 Durable Object (workerd) で動かす検証。`npm run test:workers`。
// STORE_KEY はテスト専用の固定値 (32 バイトの base64url)。本番の鍵ではない。
// LIVE_* は本番の wrangler.toml の値に依らず dry-run に固定する (このテストは GitHub へ書き込まない前提)。
export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: "./wrangler.toml" },
      miniflare: {
        bindings: { STORE_KEY: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", LIVE_LAUNCH: "0", LIVE_DISPATCH: "0" },
      },
    }),
  ],
  test: {
    include: ["test/runtime/**/*.test.ts"],
  },
});
