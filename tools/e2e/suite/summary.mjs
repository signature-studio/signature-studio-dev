#!/usr/bin/env node
// work/results/*.json を Markdown 表にする (GitHub Actions の $GITHUB_STEP_SUMMARY 用)。
//   node suite/summary.mjs [<title>] >> "$GITHUB_STEP_SUMMARY"
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";

const dir = path.resolve(import.meta.dirname, "../work/results");
const title = process.argv[2] ?? "E2E";
const files = existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith(".json")).sort() : [];

console.log(`### ${title}\n`);
if (files.length === 0) {
  console.log("結果 JSON なし (ビルド/起動で失敗した可能性。ログを参照)");
  process.exit(0);
}
console.log("| target | driver | PASS | FAIL | SKIP | FAIL した check |");
console.log("|---|---|---:|---:|---:|---|");
for (const f of files) {
  const r = JSON.parse(readFileSync(path.join(dir, f), "utf8"));
  const n = (s) => r.results.filter((x) => x.status === s).length;
  const failed = r.results.filter((x) => x.status === "FAIL").map((x) => x.id).join(", ");
  console.log(`| ${r.target} | ${r.driverVersion} | ${n("PASS")} | ${n("FAIL")} | ${n("SKIP")} | ${failed} |`);
}
