#!/usr/bin/env bash
# #437: REPORT 分割の検査。REPORT*.md が 250 行以下、かつ分割前 (BASE) の全非空行が分割後 3 ファイルに残ること。
# 例外は「行数に関する注記 3 行」(分割で意図的に書き換え) のみで、先頭 12 文字の固定接頭辞で完全に限定する。
# 比較は重複行も数える多重集合 (sort のみ・-u なし)。
# 基準・対象のいずれかを読めない場合は検査不能として exit 1 (fail-closed)。
# 使い方: bash report_split_check.sh [BASE_COMMIT] [REV]  (既定 BASE=e3b9202 = 分割前 main, REV=HEAD)。不合格は exit 1。
set -euo pipefail
export LC_ALL=C
BASE=${1:-e3b9202}; REV=${2:-HEAD}; D=tools/hostbridge/nfo; rc=0
FILES="REPORT.md REPORT_APPENDIX_A.md REPORT_APPENDIX_B.md"
git cat-file -e "$BASE:$D/REPORT.md" 2>/dev/null \
  || { echo "FAIL: cannot read BASE $BASE:$D/REPORT.md (shallow clone? fetch-depth: 0 が必要)"; exit 1; }
for f in $FILES; do
  git cat-file -e "$REV:$D/$f" 2>/dev/null || { echo "FAIL: cannot read $REV:$D/$f"; exit 1; }
done
nbase=$(git show "$BASE:$D/REPORT.md" | grep -vc '^$' || true)
[ "$nbase" -gt 0 ] || { echo "FAIL: BASE $BASE:$D/REPORT.md has 0 non-empty lines"; exit 1; }
for f in $FILES; do
  n=$(git show "$REV:$D/$f" | wc -l); echo "$f $REV lines=$n"
  [ "$n" -le 250 ] || { echo "FAIL: $f > 250"; rc=1; }
done
allowed='^(> \*\*行数目安\*\*: |> 超過分は Git 履歴に残る形での|- 行数: 本 REPORT は 250 行上限)'
lost=$(comm -23 \
    <(git show "$BASE:$D/REPORT.md" | grep -v '^$' | sort) \
    <(for f in $FILES; do git show "$REV:$D/$f"; done | sort) \
  | { grep -Ev "$allowed" || true; })
nlost=$(printf '%s' "$lost" | grep -c '^' || true)
echo "lost non-empty lines (multiset) vs $BASE (excluding 3 allowed 行数注記): $nlost"
[ "$nlost" -eq 0 ] || { echo "FAIL: content lost"; printf '%s\n' "$lost" | cut -c1-100; rc=1; }
exit $rc
