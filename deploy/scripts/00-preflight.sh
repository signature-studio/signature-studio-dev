#!/usr/bin/env bash
# 事前確認 (読取のみ・何も作らない): cf / wrangler 認証 / 必要スコープ / 既存 Worker・Access の衝突
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
WORKER_NAME="${WORKER_NAME:-signature-studio}"

step "cf CLI / 認証スコープ"
command -v cf >/dev/null || { echo "cf が無い (bun add -g cf)"; exit 2; }
cf auth whoami | node -e '
const w = JSON.parse(require("fs").readFileSync(0, "utf8"));
const need = ["workers-scripts.write","access-app.write","access-service-token.write","access-app.read"];
const have = new Set(w.scopes ?? []);
console.log("authenticated:", w.authenticated, "source:", w.authSource);
if (!w.scopes) console.log("(OAuth スコープ情報なし = API トークン運用。Account: Workers Scripts Edit / Access: Apps and Policies Edit / Access: Service Tokens Edit を付与)");
else for (const s of need) console.log((have.has(s) ? "  OK  " : "  MISSING ") + s);
process.exit(w.scopes && need.some((s) => !have.has(s)) ? 1 : 0);
' || { echo "スコープ不足: cf auth login をやり直すか deploy/README.md のトークン権限を参照"; exit 1; }

step "wrangler 認証 (bunx wrangler whoami)"
(cd "$DEPLOY_DIR" && bunx wrangler whoami 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E "logged in|workers \(write\)|workers_scripts \(write\)" | head -3) || true

step "既存 Worker / Access の衝突確認 ($WORKER_NAME)"
cf workers scripts search --name "$WORKER_NAME" --per-page 100 | WORKER_NAME="$WORKER_NAME" node -e '
const l = JSON.parse(require("fs").readFileSync(0, "utf8")); const n = process.env.WORKER_NAME;
console.log(l.some((s) => s.script_name === n) ? "  既に存在: " + n + " (再デプロイ。asset は差分のみ)" : "  未作成: " + n + " (新規作成)");'
cf zero-trust access applications list | WORKER_NAME="$WORKER_NAME" node -e '
const l = JSON.parse(require("fs").readFileSync(0, "utf8")); const n = process.env.WORKER_NAME;
const hit = l.find((a) => a.name === n);
console.log("  Access apps: " + l.length + " 件 (うち本構成: " + (hit ? "あり -> 40-access が更新" : "なし -> 新規作成") + "。他アプリは変更しない)");'
echo "OK (読取のみ)"
