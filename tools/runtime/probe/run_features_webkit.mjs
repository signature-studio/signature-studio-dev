#!/usr/bin/env node
// WebKit (Playwright 同梱 WebKit、Linux) 機能マトリクス実測。Safari 実機ではない参考値:
//   PLAYWRIGHT_CORE=<playwright-core の index.mjs> node tools/runtime/probe/run_features_webkit.mjs  → work/features_result_webkit.json
// PLAYWRIGHT_CORE 未指定時は "playwright-core" を解決する。WebKit 本体は `playwright install --with-deps webkit` で取得する。
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { writeFileSync, mkdirSync } from "node:fs";
import { serve } from "../lib/serve.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const pwPath = process.env.PLAYWRIGHT_CORE ? pathToFileURL(process.env.PLAYWRIGHT_CORE).href : "playwright-core";
const { webkit } = await import(pwPath);
const srv = await serve([{ prefix: "/", dir: here }]);
const browser = await webkit.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.goto(`http://127.0.0.1:${srv.port}/features.html`, { waitUntil: "commit" });
  await page.waitForFunction(() => window.__result, null, { timeout: 120000, polling: 200 }).catch(async (e) => {
    const last = await page.evaluate(() => window.__step + " | " + JSON.stringify(window.__partial)).catch(() => "?");
    throw new Error("waitFor(__result) timeout; last step / partial: " + last + " / " + e.message);
  });
  const out = JSON.parse(await page.evaluate(() => JSON.stringify(window.__result)));
  out.webkit = browser.version();
  mkdirSync(path.join(here, "../work"), { recursive: true });
  writeFileSync(path.join(here, "../work/features_result_webkit.json"), JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 1));
} finally {
  await browser.close();
  await srv.close();
}
