#!/usr/bin/env node
// 生産した manifest と 05-stage が出した release.json (files/chunked の sha256) を突合する。
//   node tools/assets/deploy-manifest/verify-release.mjs <deploy-manifest.json> <release.json>
// 05-stage とは別経路 (manifest の sha256 は make-manifest が先に計算、release.json は stage が配備物から再計算) の検算。
import { readFileSync } from "node:fs";

export function verify(manifest, release) {
  const problems = [];
  const seen = new Set();
  for (const f of manifest.files) {
    const r = release.files?.[f.path] ?? release.chunked?.[f.path];
    if (!r) { problems.push(`release.json に無い: ${f.path}`); continue; }
    seen.add(f.path);
    if (r.sha256 !== f.sha256) problems.push(`sha256 不一致: ${f.path} (manifest ${f.sha256.slice(0, 12)} / release ${r.sha256.slice(0, 12)})`);
    if (r.size !== f.size) problems.push(`size 不一致: ${f.path} (${f.size} / ${r.size})`);
    if (r.contentType !== f.contentType) problems.push(`contentType 不一致: ${f.path} (${f.contentType} / ${r.contentType})`);
  }
  return { checked: seen.size, problems };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const [mf, rf] = process.argv.slice(2);
  if (!mf || !rf) { console.error("usage: verify-release.mjs <deploy-manifest.json> <release.json>"); process.exit(1); }
  const r = verify(JSON.parse(readFileSync(mf, "utf8")), JSON.parse(readFileSync(rf, "utf8")));
  if (r.problems.length) { console.error(r.problems.join("\n")); process.exit(2); }
  console.log(`verify-release: ${r.checked} files OK`);
}
