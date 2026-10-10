#!/usr/bin/env node
// 巨大 wasm のコンパイル/起動コストとキャッシュ挙動を Chrome 実機で測る。
//   python3 bench/make_big_wasm.py … で work/big/*.wasm を作った後: node tools/runtime/bench/run_compile_bench.mjs
import path from "node:path"; import { fileURLToPath } from "node:url"; import { writeFileSync, readdirSync, mkdtempSync, copyFileSync } from "node:fs";
import { serve } from "../lib/serve.mjs"; import { launchChrome } from "../lib/chrome.mjs";
const here = path.dirname(fileURLToPath(import.meta.url)), rt = path.resolve(here, "..");
const bigDir = path.join(rt, "work/big");
const files = readdirSync(bigDir).filter((f) => f.endsWith(".wasm")).sort((a, b) => a.length - b.length || a.localeCompare(b));
const srv = await serve([{ prefix: "/bench/", dir: here }, { prefix: "/lib/", dir: path.join(rt, "lib") }, { prefix: "/big/", dir: bigDir }],
  { headers: { "Cache-Control": "public, max-age=31536000, immutable" } });
const base = `http://127.0.0.1:${srv.port}/bench/compile_page.html`;
const prof = mkdtempSync("/tmp/opencode/chrome-cache-prof-");
const all = {};
try {
  const chrome = await launchChrome({ userDataDir: prof });
  const runOnce = async (label, query) => { const p = await chrome.newPage(`${base}?${query}`); const r = await p.waitFor("__result", 600000); await chrome.browser.send("Target.closeTarget", { targetId: p.targetId }); all[label] = r; return r; };
  // (1) 同一プロファイルで 3 回連続 streaming compile (HTTP キャッシュ/コードキャッシュ効果)
  for (let i = 1; i <= 3; i++) await runOnce(`streaming_run${i}`, `files=${files.join(",")}&mode=streaming&run=1`);
  // (2) bytes → compile
  await runOnce("bytes_run1", `files=${files.join(",")}&mode=bytes&run=1`);
  await chrome.close();
  // (3) ブラウザ再起動後 (disk cache のみ残る) の streaming
  const chrome2 = await launchChrome({ userDataDir: prof });
  const p = await chrome2.newPage(`${base}?files=${files.join(",")}&mode=streaming&run=1`);
  all["streaming_after_restart"] = await p.waitFor("__result", 600000);
  await chrome2.close();
} finally { await srv.close(); }
writeFileSync(path.join(rt, "work/compile_bench_result.json"), JSON.stringify(all, null, 1));
const sizes = Object.fromEntries(files.map((f) => [f, (readdirSync(bigDir).length, 0)]));
for (const [label, rs] of Object.entries(all)) {
  console.log(`\n== ${label}`);
  console.table(rs.map((r) => ({ file: r.file, ok: r.ok, "fetch+compile ms": r.fetchCompileMs, "compileOnly(bytes) ms": r.compileOnlyMs, "instantiate ms": r.instantiateMs, "1st call ms": r.firstCallMs, "2nd call ms": r.secondCallMs, transfer: r.transferSize, delivery: r.deliveryType })));
}
process.exit(0);
