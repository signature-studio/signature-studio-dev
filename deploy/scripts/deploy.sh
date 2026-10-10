#!/usr/bin/env bash
# 配信一括実行 (Workers Static Assets)。既定は DRY-RUN (書込なし)。
#   bash deploy/scripts/deploy.sh --src tools/e2e/work/dist [--manifest tools/assets/manifest.json]
#   APPLY=1 bash deploy/scripts/deploy.sh --src ...        # 実デプロイ (CAB-35。ユーザ承認後のみ)
#
# 順序の理由 (公開 URL が出来る瞬間に Access が掛かっているようにする):
#   05 stage -> 20 closed(placeholder, URL 無し) -> 40 access(worker 型) -> 20 open(placeholder 公開, 無認証 302 まで待つ)
#   -> 20 release(本物の asset) -> 90 verify
#   (workers.dev 有効化直後は Access が効くまで無認証 200 が数秒出ることがある: 実測。本物の asset はその後に載せる)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib.sh"
WORKER_NAME="${WORKER_NAME:-signature-studio}"; export WORKER_NAME
# ACCESS_ALLOW_EMAILS は任意 (未指定なら Access の人間ポリシーは include: Everyone。40-access.mjs 参照)

bash "$HERE/00-preflight.sh"

step "stage (deploy/work/site)"
node "$HERE/05-stage.mjs" "$@"

if [[ "$APPLY" == "1" ]]; then
  node "$HERE/20-worker.mjs" --phase closed
  node "$HERE/40-access.mjs" --apply
  node "$HERE/20-worker.mjs" --phase open
  node "$HERE/20-worker.mjs" --phase release
  bash "$HERE/90-verify.sh"
else
  node "$HERE/20-worker.mjs" --phase closed --dry-run
  node "$HERE/40-access.mjs" --dry-run
  echo; echo "DRY-RUN 完了 (Cloudflare 側は変更なし)。実行は APPLY=1。公開後検証: bash deploy/scripts/90-verify.sh"
fi
