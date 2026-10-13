#!/usr/bin/env bash
# #378: REPORT.md 分割が無損失であることを検査する (不一致なら非ゼロ終了)。
# 使い方: bash tools/plugins/p0c/check_report_split.sh [分割前 commit (既定 ad4b10d)]
# 既定を ad4b10d にしたのは main で §15.4 (#360) が分割前の REPORT.md に追記されたため (8f55002 からの差分は §15.4 のみ)。
# 検査: (1) 分割前 REPORT.md の §8 以降 == 付録 A〜F (各先頭 4 行を除く) の連結
#       (2) 分割前 §1〜§7 == 現 REPORT.md の対応範囲
#       (3) REPORT.md が 250 行以内
#       (4) NEGATIVE=1 で付録連結から 1 行落として (1) が FAIL することを確認
set -euo pipefail
BASE=${1:-ad4b10d}
D=$(cd "$(dirname "$0")" && pwd)
REL=tools/plugins/p0c/REPORT.md
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
git -C "$D" show "$BASE:$REL" > "$T/orig.md"
start=$(grep -n '^## 8\. ' "$T/orig.md" | head -1 | cut -d: -f1)
head -n $((start-1)) "$T/orig.md" > "$T/orig_head.md"
tail -n +"$start" "$T/orig.md" > "$T/orig_tail.md"
for x in A B C D E F; do tail -n +5 "$D/REPORT_APPENDIX_$x.md"; done > "$T/cat.md"
fail=0
cmp -s "$T/orig_tail.md" "$T/cat.md" && echo "PASS tail==appendix ($(wc -l < "$T/cat.md") lines)" || { echo "FAIL tail!=appendix"; fail=1; }
# 本体は先頭注記 (3 行→2 行) と末尾の付録索引だけが違う: §1〜§7 本文 (「作成:」行以降) を比較
n_orig=$(grep -n '^作成: ' "$T/orig_head.md" | head -1 | cut -d: -f1)
n_new=$(grep -n '^作成: ' "$D/REPORT.md" | head -1 | cut -d: -f1)
idx=$(grep -n '^## 8〜16\. 付録索引' "$D/REPORT.md" | cut -d: -f1)
diff -q <(tail -n +"$n_orig" "$T/orig_head.md" | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}') \
        <(sed -n "${n_new},$((idx-1))p" "$D/REPORT.md" | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}') >/dev/null \
  && echo "PASS body(§1-§7) unchanged" || { echo "FAIL body changed"; fail=1; }
lines=$(wc -l < "$D/REPORT.md")
[ "$lines" -le 250 ] && echo "PASS REPORT.md $lines lines <= 250" || { echo "FAIL REPORT.md $lines lines > 250"; fail=1; }
if [ "${NEGATIVE:-0}" = 1 ]; then
  sed '100d' "$T/cat.md" > "$T/broken.md"
  if cmp -s "$T/orig_tail.md" "$T/broken.md"; then echo "FAIL negative control did not fail"; fail=1; else echo "PASS negative control detected (1 line dropped)"; fi
fi
exit $fail
