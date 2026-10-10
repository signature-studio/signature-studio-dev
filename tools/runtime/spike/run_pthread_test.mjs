#!/usr/bin/env node
import path from "node:path"; import { fileURLToPath } from "node:url";
import { serve } from "../lib/serve.mjs"; import { launchChrome } from "../lib/chrome.mjs";
const here = path.dirname(fileURLToPath(import.meta.url)), rt = path.resolve(here, "..");
const srv = await serve([{ prefix: "/pt/", dir: path.join(rt, "work/pthread") }, { prefix: "/", dir: here }]);
const chrome = await launchChrome();
try {
  const page = await chrome.newPage(`http://127.0.0.1:${srv.port}/pthread_page.html`);
  const r = await page.waitFor("__result", 120000);
  console.log(JSON.stringify(r, null, 1));
} finally { await chrome.close(); await srv.close(); }
