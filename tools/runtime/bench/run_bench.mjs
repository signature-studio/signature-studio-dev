#!/usr/bin/env node
// Chrome 上で wasm32 vs wasm64 ベンチ (Worker 内)。前提: bash build_ott_variants.sh と membench ビルド済み。
import path from "node:path"; import { fileURLToPath } from "node:url"; import { writeFileSync } from "node:fs";
import { serve } from "../lib/serve.mjs"; import { launchChrome } from "../lib/chrome.mjs";
const here = path.dirname(fileURLToPath(import.meta.url)), rt = path.resolve(here, "..");
const srv = await serve([{ prefix: "/bench/", dir: here }, { prefix: "/work/", dir: path.join(rt, "work") }, { prefix: "/lib/", dir: path.join(rt, "lib") }]);
const chrome = await launchChrome();
try {
  const page = await chrome.newPage(`http://127.0.0.1:${srv.port}/bench/bench.html`);
  const r = await page.waitFor("__result", 600000);
  if (!r.ok) throw new Error(r.err);
  writeFileSync(path.join(rt, "work/bench_result.json"), JSON.stringify(r.r, null, 2));
  console.log(JSON.stringify(r.r, null, 1));
} finally { await chrome.close(); await srv.close(); }
