#!/usr/bin/env bash
# m11_remap_count.py のネガティブコントロール。
#  (a) 既知の未 remap 即値 (image VA 0x400000) を 1 行だけ含む IR で、--assert-clean が exit 1 かつ
#      "FAIL: unremapped image-VA inttoptr = 1" を標準出力に出すこと (件数 1 の検出能力の確認)。
#  (b) 未 remap 即値を含まない IR で exit 0 になること (検出器が常に落ちるだけ、を弾く)。
# 検出器の欠落・トレースバック・常時 FAIL はいずれも非 0 で終わる。
set -u
cd "$(dirname "$0")"
TMP=$(mktemp)
CLEAN=$(mktemp)
OUT=$(mktemp)
trap 'rm -f "$TMP" "$CLEAN" "$OUT"' EXIT
printf '%%p = inttoptr i64 4194304 to ptr\n' > "$TMP"
printf '%%p = inttoptr i64 33554432 to ptr\n' > "$CLEAN"

python3 m11_remap_count.py "$TMP" --assert-clean > "$OUT" 2>&1
rc=$?
if [ "$rc" -ne 1 ] || ! grep -qxF 'FAIL: unremapped image-VA inttoptr = 1' "$OUT"; then
  echo "NEGCTL FAIL: 既知の未 remap 即値 (件数 1) を検出できなかった (exit=$rc)"
  cat "$OUT"
  exit 1
fi

python3 m11_remap_count.py "$CLEAN" --assert-clean > "$OUT" 2>&1
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "NEGCTL FAIL: 未 remap 即値を含まない IR で非 0 になった (exit=$rc)"
  cat "$OUT"
  exit 1
fi
echo "NEGCTL OK: 既知の未 remap 即値 (件数 1) で exit 1 かつ FAIL 行、clean IR で exit 0"
