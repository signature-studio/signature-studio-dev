#!/usr/bin/env bash
# #437: REPORT 分割の検査。REPORT*.md が 250 行以下、かつ分割前 (BASE) の全非空行が分割後 3 ファイルに残ること。
# 使い方: bash report_split_check.sh [BASE_COMMIT]  (既定 e3b9202 = 分割前 main)。不合格は exit 1。
set -u
BASE=${1:-e3b9202}; D=tools/hostbridge/nfo; rc=0
for f in REPORT.md REPORT_APPENDIX_A.md REPORT_APPENDIX_B.md; do
  n=$(git show HEAD:$D/$f | wc -l); echo "$f HEAD lines=$n"
  [ "$n" -le 250 ] || { echo "FAIL: $f > 250"; rc=1; }
done
miss=$(git show $BASE:$D/REPORT.md | grep -v '^$' | sort -u | comm -23 - <(for f in REPORT.md REPORT_APPENDIX_A.md REPORT_APPENDIX_B.md; do git show HEAD:$D/$f; done | sort -u) | wc -l)
echo "lost distinct non-empty lines vs $BASE: $miss"
[ "$miss" -eq 0 ] || { echo "FAIL: content lost"; rc=1; }
exit $rc
