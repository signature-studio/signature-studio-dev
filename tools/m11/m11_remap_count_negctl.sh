#!/usr/bin/env bash
# m11_remap_count.py のネガティブコントロール: 既知の未 remap 即値 (image VA 0x400000) を 1 行足した IR で
# --assert-clean が必ず非 0 になることを確認する。検出できなければ非 0 で終わる (不合格を握りつぶさない)。
set -u
cd "$(dirname "$0")"
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
printf '%%p = inttoptr i64 4194304 to ptr\n' > "$TMP"
if python3 m11_remap_count.py "$TMP" --assert-clean > /dev/null; then
  echo "NEGCTL FAIL: 既知の未 remap 即値を検出できなかった"
  exit 1
fi
echo "NEGCTL OK: 既知の未 remap 即値で --assert-clean が非 0 になった"
