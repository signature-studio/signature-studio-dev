#!/usr/bin/env bash
# 配信後検証: tools/e2e の同一スイートを実 URL に対して agent-browser で実行する。
# Access 保護時は service token (deploy/work/secrets/<name>.json) を自動で渡す。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need CF_HOSTNAME

SECRET="$DEPLOY_DIR/work/secrets/${ACCESS_SERVICE_TOKEN_NAME:-webstudio-e2e}.json"
if [[ -z "${E2E_ACCESS_CLIENT_ID:-}" && -f "$SECRET" ]]; then
  E2E_ACCESS_CLIENT_ID="$(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1],"utf8")).client_id)' "$SECRET")"
  E2E_ACCESS_CLIENT_SECRET="$(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1],"utf8")).client_secret)' "$SECRET")"
  export E2E_ACCESS_CLIENT_ID E2E_ACCESS_CLIENT_SECRET
fi

step "ヘッダ確認 https://$CF_HOSTNAME/"
HDR=()
[[ -n "${E2E_ACCESS_CLIENT_ID:-}" ]] && HDR=(-H "CF-Access-Client-Id: $E2E_ACCESS_CLIENT_ID" -H "CF-Access-Client-Secret: $E2E_ACCESS_CLIENT_SECRET")
curl -sSI "${HDR[@]}" "https://$CF_HOSTNAME/" | grep -iE "^(HTTP|cross-origin|cache-control|content-type|content-encoding|cf-cache-status|cf-access)" || true

step "E2E (agent-browser, 実 URL)"
exec bash "$REPO_ROOT/tools/e2e/run.sh" --url "https://$CF_HOSTNAME" "$@"
