#!/bin/bash
# fetch-artifacts-noretry.sh — #3976 より前の取得 loop (action.yml の旧 L125-L135) をそのまま script にしたもの。
# ネガコン専用: test-fetch-artifacts.sh が FETCH_SCRIPT 経由で当てる。再試行も部分取得の検出も無い。
set -uo pipefail

artifacts_dir="$1"
endpoint="https://${CF_ACCOUNT_ID}.r2.cloudflarestorage.com"
missing=""
for name in ${R2_ARTIFACTS:-}; do
  case "$name" in apt-*) continue ;; esac
  key="artifacts/${name}.tar.zst"
  if aws s3 cp "s3://${R2_BUCKET}/$key" "$artifacts_dir" \
    --endpoint-url "$endpoint" --only-show-errors; then
    echo "fetched $key"
  else
    missing="$missing $key"
  fi
done
if [ -n "$missing" ]; then
  echo "::error::missing R2 object(s) in s3://${R2_BUCKET}:$missing"
  exit 1
fi
