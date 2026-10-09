#!/usr/bin/env bash
# 出力比較スクリプト M1 用。
# 使い方: compare.sh <reference> <actual1> [actual2 ...]
#   すべての actual の内容が reference と一致すれば exit 0、1つでも不一致なら詳細表示して exit 1。

set -euo pipefail

TAG="[M1]"

die() { echo "$TAG FAIL: $*" >&2; exit 1; }

[ $# -ge 2 ] || die "usage: compare.sh <reference> <actual1> [actual2 ...]"

REF="$1"; shift
[ -f "$REF" ] || die "reference ファイルがありません: $REF"

FAILED=0
for f in "$@"; do
    if cmp -s "$REF" "$f"; then
        echo "$TAG MATCH: $f"
    else
        echo "$TAG MISMATCH: $f" >&2
        echo "$TAG --- reference ($(basename "$REF")) ---" >&2
        cat "$REF" >&2
        echo "$TAG --- $f ---" >&2
        cat "$f" >&2
        FAILED=1
    fi
done

[ "$FAILED" -eq 0 ] || die "出力不一致あり"
exit 0
