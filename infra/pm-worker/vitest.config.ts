import { defineConfig } from "vitest/config";
import { cloudflareTest } from "@cloudflare/vitest-plugin";

// 実 Durable Object (workerd) で動かす検証。`npm run test:workers`。
// STORE_KEY はテスト専用の固定値 (32 バイトの base64url)。本番の鍵ではない。
export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: "./wrangler.toml" },
      miniflare: {
        bindings: { STORE_KEY: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" },
      },
    }),
  ],
  test: {
    include: ["test/runtime/**/*.test.ts"],
  },
});
