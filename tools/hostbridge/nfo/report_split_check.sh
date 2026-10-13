#!/usr/bin/env bash
# #437: REPORT 分割の検査。REPORT*.md が 250 行以下、かつ分割前 (BASE) の全非空行が分割後 3 ファイルに残ること。
# 例外は「行数に関する注記 3 行」(分割で意図的に書き換え) のみで、先頭 12 文字の固定接頭辞で完全に限定する。
# 使い方: bash report_split_check.sh [BASE_COMMIT] [REV]  (既定 BASE=e3b9202 = 分割前 main, REV=HEAD)。不合格は exit 1。
set -u
BASE=${1:-e3b9202}; REV=${2:-HEAD}; D=tools/hostbridge/nfo; rc=0
for f in REPORT.md REPORT_APPENDIX_A.md REPORT_APPENDIX_B.md; do
  n=$(git show "$REV:$D/$f" | wc -l); echo "$f $REV lines=$n"
  [ "$n" -le 250 ] || { echo "FAIL: $f > 250"; rc=1; }
done
allowed='^(> \*\*行数目安\*\*: |> 超過分は Git 履歴に残る形での|- 行数: 本 REPORT は 250 行上限)'
lost=$(git show "$BASE:$D/REPORT.md" | grep -v '^$' | sort -u \
  | comm -23 - <(for f in REPORT.md REPORT_APPENDIX_A.md REPORT_APPENDIX_B.md; do git show "$REV:$D/$f"; done | sort -u) \
  | grep -Ev "$allowed")
nlost=$(printf '%s' "$lost" | grep -c '^' || true)
echo "lost distinct non-empty lines vs $BASE (excluding 3 allowed 行数注記): $nlost"
[ "$nlost" -eq 0 ] || { echo "FAIL: content lost"; printf '%s\n' "$lost" | cut -c1-100; rc=1; }
exit $rc
