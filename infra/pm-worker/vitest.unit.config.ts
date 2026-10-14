import { defineConfig } from "vitest/config";

// fetch をモックした Node の単体テスト (test/unit)。workerd は使わない (実 Durable Object は vitest.config.ts の test:workers で見る)。
export default defineConfig({
  test: {
    include: ["test/unit/**/*.test.ts"],
    environment: "node",
  },
});
