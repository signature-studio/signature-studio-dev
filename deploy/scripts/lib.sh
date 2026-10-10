#!/usr/bin/env bash
# deploy/ 共通: .env 読込 + dry-run 切替。source して使う。
#   APPLY=1 で実行、未指定は DRY (cf --dry-run 付与 / 書込コマンドは表示のみ)
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$DEPLOY_DIR/.." && pwd)"
[[ -f "$DEPLOY_DIR/.env" ]] && { set -a; source "$DEPLOY_DIR/.env"; set +a; }
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"

APPLY="${APPLY:-0}"
DRYFLAG=(--dry-run)
[[ "$APPLY" == "1" ]] && DRYFLAG=()

need() { for v in "$@"; do [[ -n "${!v:-}" ]] || { echo "環境変数が未設定: $v (deploy/env.example 参照)" >&2; exit 2; }; done; }
step() { printf '\n## %s [%s]\n' "$*" "$([[ $APPLY == 1 ]] && echo APPLY || echo DRY-RUN)"; }
