#!/usr/bin/env node
// Chrome 機能マトリクス実測: node tools/runtime/probe/run_features.mjs  → work/features_result.json
import path from "node:path";
import { fileURLToPath } from "node:url";
import { writeFileSync, mkdirSync } from "node:fs";
import { serve } from "../lib/serve.mjs";
import { launchChrome } from "../lib/chrome.mjs";
const here = path.dirname(fileURLToPath(import.meta.url));
const srv = await serve([{ prefix: "/", dir: here }]);
const chrome = await launchChrome();
try {
  const page = await chrome.newPage(`http://127.0.0.1:${srv.port}/features.html`);
  const r = await page.waitFor("__result", 120000);
  r.chrome = chrome.version;
  r.pageExceptions = page.exceptions;
  mkdirSync(path.join(here, "../work"), { recursive: true });
  writeFileSync(path.join(here, "../work/features_result.json"), JSON.stringify(r, null, 2));
  console.log(JSON.stringify(r, null, 1));
} finally { await chrome.close(); await srv.close(); }
