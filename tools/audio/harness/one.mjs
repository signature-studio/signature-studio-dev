// 単発実行: node harness/one.mjs "api=asio&mode=sine&buf=256&secs=5"
import { withChrome } from "./chrome.mjs";
import fs from "node:fs"; import path from "node:path"; import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const qs = process.argv[2] ?? "api=asio&mode=sine&buf=256&secs=5";
const r = await withChrome({ root: path.join(here, "../build/web"), page: "index.html?" + qs, log: (s) => fs.appendFileSync(process.env.FLA_LOG ?? "/tmp/opencode/one.log", s + "\n") },
  (c) => c.eval("window.__done"));
console.log(JSON.stringify(r, null, 1));
