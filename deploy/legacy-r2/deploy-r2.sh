#!/usr/bin/env bash
# 配信一括実行。既定は DRY-RUN (読取 API のみ実呼び出し、書込は cf --dry-run / 計画表示)。
#   bash deploy/legacy-r2/deploy-r2.sh --src tools/e2e/work/dist [--manifest tools/assets/manifest.json] [--backend cf|aws]
#   APPLY=1 bash deploy/legacy-r2/deploy-r2.sh --src dist ...      # 実デプロイ (要 deploy/.env と Cloudflare 認証)
#
# 順序の理由:
#   10 bucket -> 20 upload -> 40 access -> 30 rules -> 50 domain(公開) -> 90 verify
#   Access と rules(COOP/COEP/index rewrite/cache) を **公開前に**用意する。
#   (bucket がカスタムドメイン接続時点で無保護/ヘッダ無しになるのを避ける)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/../scripts/lib.sh"
need CF_ZONE CF_HOSTNAME CF_R2_BUCKET

UPLOAD_ARGS=("$@")
MODE_FLAGS=(); RULE_MODE="--dry-run"; ACCESS_MODE="--dry-run"
if [[ "$APPLY" == "1" ]]; then RULE_MODE="--apply"; ACCESS_MODE="--apply"; MODE_FLAGS=(--execute --skip-existing --purge); fi

bash "$HERE/00-preflight.sh"
bash "$HERE/10-bucket.sh"
node "$HERE/20-upload.mjs" --bucket "$CF_R2_BUCKET" --zone "$CF_ZONE" --host "$CF_HOSTNAME" "${UPLOAD_ARGS[@]}" "${MODE_FLAGS[@]}"
node "$HERE/40-access.mjs" --host "$CF_HOSTNAME" $ACCESS_MODE
node "$HERE/30-rulesets.mjs" --host "$CF_HOSTNAME" --zone "$CF_ZONE" $RULE_MODE
bash "$HERE/50-domain.sh"
if [[ "$APPLY" == "1" ]]; then
  bash "$HERE/../scripts/90-verify.sh"
else
  echo; echo "DRY-RUN 完了。実行は APPLY=1 を付ける。公開後検証: bash deploy/scripts/90-verify.sh"
fi
