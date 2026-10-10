#!/usr/bin/env bash
# 事前確認 (読取のみ・何も作らない): cf / 認証 / 必要スコープ / zone / 既存衝突
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib.sh"
need CF_ZONE CF_HOSTNAME CF_R2_BUCKET

step "cf CLI"
command -v cf >/dev/null || { echo "cf が無い (bun add -g cf)"; exit 2; }
cf --version

step "認証 (cf auth whoami)"
WHO="$(cf auth whoami)"
echo "$WHO" | node -e '
const w = JSON.parse(require("fs").readFileSync(0, "utf8"));
const need = ["workers-r2.write","workers-r2-bucket-item.write","zone-transform-rules.write","cache-settings.write","response-compression.write","cache.purge","access-app.write","access-policy.write","access-service-token.write","dns.write","zone.read"];
const have = new Set(w.scopes ?? []);
console.log("authenticated:", w.authenticated, "source:", w.authSource);
if (!w.scopes) console.log("(OAuth スコープ情報なし = API トークン運用。下記権限をトークンに付与すること)");
else for (const s of need) console.log((have.has(s) ? "  OK  " : "  MISSING ") + s);
process.exit(w.scopes && need.some((s) => !have.has(s)) ? 1 : 0);
' || { echo "スコープ不足: cf auth login をやり直すか deploy/README.md のトークン権限を参照"; exit 1; }

step "zone 解決 / 既存衝突チェック"
cf zones list --name "$CF_ZONE" | node -e '
const z = JSON.parse(require("fs").readFileSync(0, "utf8")); const l = Array.isArray(z) ? z : z.result ?? [];
if (!l.length) { console.error("zone が見つからない: " + process.env.CF_ZONE); process.exit(1); }
console.log("zone:", l[0].name, "status:", l[0].status, "plan:", l[0].plan?.name ?? "(n/a)");'
echo "bucket 既存確認:"
cf r2 buckets list | node -e '
const b = JSON.parse(require("fs").readFileSync(0, "utf8")).buckets ?? [];
const hit = b.find((x) => x.name === process.env.CF_R2_BUCKET);
console.log(hit ? "  既に存在: " + hit.name + " (10-bucket は冪等にスキップ)" : "  未作成 (10-bucket で作成)");'
echo "hostname の DNS 衝突確認:"
cf dns records list -z "$CF_ZONE" --name "$CF_HOSTNAME" 2>&1 | head -5 || true
echo "OK (読取のみ)"
