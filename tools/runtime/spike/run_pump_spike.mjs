#!/usr/bin/env node
// ブロッキング GetMessage 4 方式 (Atomics.wait / native wasm wait / JSPI / Asyncify) の実機比較。
//   bash tools/runtime/spike/build_pump_spike.sh && node tools/runtime/spike/run_pump_spike.mjs
import path from "node:path"; import { fileURLToPath } from "node:url"; import { writeFileSync } from "node:fs";
const here = path.dirname(fileURLToPath(import.meta.url)), rt = path.resolve(here, "..");
process.env.RUNTIME_WASM_DIR = path.join(rt, "work/spike");
const { createServer } = await import("vite");
const { launchChrome } = await import("../lib/chrome.mjs");
const vite = await createServer({ root: path.resolve(rt, "../.."), logLevel: "warn", server: { port: 0, host: "127.0.0.1" } });
await vite.listen();
const chrome = await launchChrome();
try {
  const q = process.argv[2] ?? "";
  const page = await chrome.newPage(`http://127.0.0.1:${vite.httpServer.address().port}/tools/runtime/spike/pump_spike.html${q}`);
  const r = await page.waitFor("__result", 600000);
  if (!r.ok) throw new Error(r.err);
  writeFileSync(path.join(rt, "work/pump_spike_result.json"), JSON.stringify({ chrome: chrome.version, ...r }, null, 2));
  const rows = r.res.map((x) => ({ variant: x.variant, depth: x.depth, "rtt p50 µs": x.rttUs?.p50, "p90": x.rttUs?.p90, "p99": x.rttUs?.p99, "max": x.rttUs?.max, "burst ev/s": x.burst?.eventsPerSec, nested: x.nestedOk ? `ok (maxDepth ${x.consumer?.maxDepth}, handled ${x.consumer?.handled})` : "" }));
  console.table(rows);
} finally { await chrome.close(); await vite.close(); }
process.exit(0);
