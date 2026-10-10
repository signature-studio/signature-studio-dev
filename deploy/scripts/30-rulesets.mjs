#!/usr/bin/env node
// ゾーンレベル Rules を edge-policy.json から生成して反映する。
//   http_request_transform          : "/" -> /index.html (R2 カスタムドメインは index 解決しない)
//   http_response_headers_transform : COOP/COEP/CORP/nosniff + Cache-Control
//   http_request_cache_settings     : wasm/html/json もエッジキャッシュ (既定は拡張子限定)
//   http_response_compression       : wasm/js/css/html/json を br 優先で圧縮
//
// 全 rule は http.host eq "<HOST>" で絞り込み、ref を webstudio_<host>_ で名前空間化する。
// PUT は entrypoint 全体を置換するため、既存の他 rule は必ず読み出してマージして書き戻す。
//
//   node deploy/scripts/30-rulesets.mjs --host studio.example.com --zone example.com [mode]
//   mode: (既定) 生成 JSON を stdout | --dry-run (cf --dry-run, 既存 rule は読取) |
//         --validate (サーバ側検証のみ・永続化しない) | --apply
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import {
  buildCacheRules,
  buildCompressionRules,
  buildRewriteRules,
  buildTransformRules,
  loadPolicy,
  refPrefix,
} from "../lib/policy.mjs";
import { cf, zoneId } from "../lib/cf.mjs";

const args = process.argv.slice(2);
const opt = (n, d) => {
  const i = args.indexOf(`--${n}`);
  return i >= 0 ? args[i + 1] : d;
};
const has = (n) => args.includes(`--${n}`);
const host = opt("host", process.env.CF_HOSTNAME);
const zone = opt("zone", process.env.CF_ZONE);
if (!host) throw new Error("--host (または CF_HOSTNAME) が必要");
const mode = has("apply") ? "apply" : has("validate") ? "validate" : has("dry-run") ? "dry-run" : "print";
const policy = loadPolicy();

const phases = [
  ["http_request_transform", buildRewriteRules(policy, host)],
  ["http_response_headers_transform", buildTransformRules(policy, host)],
  ["http_request_cache_settings", buildCacheRules(policy, host)],
  ["http_response_compression", buildCompressionRules(policy, host)],
];

if (mode === "print") {
  console.log(JSON.stringify(Object.fromEntries(phases), null, 2));
  process.exit(0);
}
if (!zone) throw new Error("--zone (または CF_ZONE) が必要");
const zid = await zoneId(zone);
const prefix = refPrefix(host);
const outDir = path.resolve(import.meta.dirname, "../work");
mkdirSync(outDir, { recursive: true });

for (const [phase, ours] of phases) {
  let existing = [];
  try {
    const cur = await cf(["rulesets", "account-rulesets", "phases", "get", phase, "-z", zid]);
    existing = cur?.rules ?? [];
  } catch (e) {
    if (!e.notFound) throw e; // entrypoint 未作成は空扱い
  }
  const foreign = existing.filter((r) => !String(r.ref ?? "").startsWith(prefix));
  // 読み出した rule のうち PUT で不要/拒否されるメタは落とす
  const keep = foreign.map(({ version, last_updated, ...r }) => r);
  const merged = [...keep, ...ours];
  const file = path.join(outDir, `${phase}.rules.json`);
  writeFileSync(file, JSON.stringify(merged, null, 2));
  const flags = ["--rules", `@${file}`];
  if (mode === "dry-run") flags.push("--dry-run");
  if (mode === "validate") flags.push("--validate-only", "true");
  console.log(
    `## ${phase}: 既存 ${existing.length} (他者 ${foreign.length}) + 本件 ${ours.length} -> ${merged.length} [${mode}]`,
  );
  const res = await cf(["rulesets", "account-rulesets", "phases", "update", phase, "-z", zid, ...flags]);
  if (mode === "dry-run") {
    console.log(`   ${res.method} ${res.url.replace(zid, "<zone-id>")}`);
  } else {
    console.log(`   OK${res?.version ? ` version=${res.version}` : ""}`);
  }
}
