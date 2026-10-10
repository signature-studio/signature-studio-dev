#!/usr/bin/env bash
# R2 バケット作成 (冪等) + r2.dev 公開 URL の無効化 + (任意) ライフサイクル
#   APPLY=1 で実行。既定は cf --dry-run。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib.sh"
need CF_R2_BUCKET

step "R2 バケット $CF_R2_BUCKET"
EXISTS="$(cf r2 buckets list | node -e 'const b=JSON.parse(require("fs").readFileSync(0,"utf8")).buckets??[];console.log(b.some(x=>x.name===process.argv[1])?1:0)' "$CF_R2_BUCKET")"
if [[ "$EXISTS" == "1" ]]; then
  echo "既に存在: skip"
else
  cf r2 buckets create-by-name "$CF_R2_BUCKET" --cf-r2-storage-class Standard "${DRYFLAG[@]}"
fi

# Access / WAF / キャッシュは r2.dev では効かない。公開 dev URL が有効なら Access を素通りするため必ず無効化。
step "r2.dev 公開 URL を無効化"
if [[ "$EXISTS" == "1" || "$APPLY" == "1" ]]; then
  cf r2 buckets domains managed update "$CF_R2_BUCKET" --enabled false "${DRYFLAG[@]}"
else
  echo "(バケット未作成のため dry-run では省略: 実行時は domains managed update --enabled false)"
fi

if [[ "${APPLY_LIFECYCLE:-0}" == "1" ]]; then
  step "ライフサイクル (legacy-r2/lifecycle.json)"
  cf r2 buckets lifecycle update "$CF_R2_BUCKET" --rules "@$DEPLOY_DIR/legacy-r2/lifecycle.json" --force "${DRYFLAG[@]}"
fi
