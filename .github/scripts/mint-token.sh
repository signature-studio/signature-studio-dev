#!/bin/bash
# mint-token.sh — GitHub App installation token を再発行して $TOKEN_FILE に書き出す。
# systemd user service (.github/systemd/token-refresh.service) から定期的に呼ばれる。
# 設定は EnvironmentFile (~/.config/token-refresh.env) 経由で受け取る。
set -euo pipefail

: "${OC_APP_ID:?OC_APP_ID is not set}"
: "${OC_APP_PRIVATE_KEY_FILE:?OC_APP_PRIVATE_KEY_FILE is not set}"

TOKEN_FILE="${TOKEN_FILE:-/tmp/gh_token}"

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

now=$(date +%s)
header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
payload=$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "$((now - 60))" "$((now + 600))" "$OC_APP_ID" | b64url)
sig=$(printf '%s.%s' "$header" "$payload" \
  | openssl dgst -sha256 -sign "$OC_APP_PRIVATE_KEY_FILE" | b64url)
jwt="$header.$payload.$sig"

api() {
  curl -fsSL -H "Authorization: Bearer $jwt" \
    -H 'Accept: application/vnd.github+json' "$@"
}

installation=$(api https://api.github.com/app/installations | jq -r '.[0].id')

# OC_TOKEN_PERMISSIONS が設定されていれば権限を制限する (read-only モード用)
permissions=()
if [ -n "${OC_TOKEN_PERMISSIONS:-}" ]; then
  permissions=(-H 'Content-Type: application/json' --data "$OC_TOKEN_PERMISSIONS")
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
api -X POST "${permissions[@]}" \
  "https://api.github.com/app/installations/$installation/access_tokens" \
  | jq -r '.token' > "$tmp"
chmod 600 "$tmp"
mv "$tmp" "$TOKEN_FILE"
