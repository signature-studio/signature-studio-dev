#!/usr/bin/env bash
# #378: REPORT.md 分割が無損失であることを検査する (不一致なら非ゼロ終了)。
# 使い方: bash tools/plugins/p0c/check_report_split.sh [分割 commit (既定 8512e3c0)]
# 検査対象は分割 commit (不変) に固定する。付録は分割後も #346/#695/#893/#982/#983 等で正当に追記されるため、
# 現 HEAD や分割前 commit (ad4b10d 等) と比べると恒久的に FAIL する (#1237)。分割後の追記は本検査の対象外。
# 250 行上限だけは現在の REPORT.md に対して検査する。
# 検査: (1) 分割 commit の付録 A〜E (各先頭 4 行を除く) の連結 == 分割前 REPORT.md の §8 以降
#       (2) 分割 commit の §1〜§7 == 分割前 REPORT.md の対応範囲 (先頭注記と付録索引は除く)
#       (3) 現 REPORT.md が 250 行以内
#       (4) NEGATIVE=1 で付録連結から 1 行落として (1) が FAIL することを確認
set -euo pipefail
S=${1:-8512e3c0}
D=$(cd "$(dirname "$0")" && pwd)
P=tools/plugins/p0c
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
git -C "$D" show "$S^:$P/REPORT.md" > "$T/orig.md"
git -C "$D" show "$S:$P/REPORT.md" > "$T/split.md"
start=$(grep -n '^## 8\. ' "$T/orig.md" | head -1 | cut -d: -f1)
head -n $((start-1)) "$T/orig.md" > "$T/orig_head.md"
tail -n +"$start" "$T/orig.md" > "$T/orig_tail.md"
for x in A B C D E; do git -C "$D" show "$S:$P/REPORT_APPENDIX_$x.md" | tail -n +5; done > "$T/cat.md"
fail=0
cmp -s "$T/orig_tail.md" "$T/cat.md" && echo "PASS tail==appendix ($(wc -l < "$T/cat.md") lines)" || { echo "FAIL tail!=appendix"; fail=1; }
# 本体は先頭注記 (3 行→2 行) と末尾の付録索引だけが違う: §1〜§7 本文 (「作成:」行以降) を比較
n_orig=$(grep -n '^作成: ' "$T/orig_head.md" | head -1 | cut -d: -f1)
n_new=$(grep -n '^作成: ' "$T/split.md" | head -1 | cut -d: -f1)
idx=$(grep -n '^## 8〜16\. 付録索引' "$T/split.md" | cut -d: -f1)
diff -q <(tail -n +"$n_orig" "$T/orig_head.md" | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}') \
        <(sed -n "${n_new},$((idx-1))p" "$T/split.md" | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}') >/dev/null \
  && echo "PASS body(§1-§7) unchanged" || { echo "FAIL body changed"; fail=1; }
lines=$(wc -l < "$D/REPORT.md")
[ "$lines" -le 250 ] && echo "PASS REPORT.md $lines lines <= 250" || { echo "FAIL REPORT.md $lines lines > 250"; fail=1; }
if [ "${NEGATIVE:-0}" = 1 ]; then
  sed '100d' "$T/cat.md" > "$T/broken.md"
  if cmp -s "$T/orig_tail.md" "$T/broken.md"; then echo "FAIL negative control did not fail"; fail=1; else echo "PASS negative control detected (1 line dropped)"; fi
fi
exit $fail
