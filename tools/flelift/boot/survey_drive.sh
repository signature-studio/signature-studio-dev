#!/usr/bin/env bash
# survey_drive.sh — hang 対策つき survey ドライバ: セグメント実行し、timeout で打ち切られたら
# 最終 unit の次から再開する (FLE-2)。セグメント結果を results/survey_seg_*.json に置き、
# 最後に merge_survey.py で統合する。
#
#   bash tools/flelift/boot/survey_drive.sh [seg_seconds] [max_segments]
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
W="$FLE/work/boot"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
SEG_SEC="${1:-180}"
MAXSEG="${2:-60}"
mkdir -p "$HERE/results"
rm -f "$HERE"/results/survey_seg_*.json "$HERE"/results/survey_seg_*.jsonl   # jsonl も消す (残すと再実行の行が重複し merge が件数を誤る・#4854)
FROM=0; SEGS=0
TOTAL=942
while [ "$FROM" -lt "$TOTAL" ] && [ "$SEGS" -lt "$MAXSEG" ]; do
  SEGS=$((SEGS + 1))
  T0=$(date +%s)
  set +e
  FLE_SURVEY_FROM=$FROM FLE_SURVEY_TO=$TOTAL timeout "$SEG_SEC" node "$HERE/fle_boot.mjs" \
    "$W/fleboot_plain.cjs" "$HERE/results/survey_seg_$FROM.json" > /dev/null 2> "$W/survey_seg_$FROM.log"
  RC=$?
  set -e
  LAST=$(grep -o '\[survey\] unit [0-9]*' "$W/survey_seg_$FROM.log" | tail -1 | awk '{print $3}')
  if [ "$RC" = 0 ]; then
    echo "[survey_drive] seg from=$FROM done ($(( $(date +%s) - T0 ))s)"
    FROM=$TOTAL
  else
    NEXT=${LAST:-$FROM}
    [ "$NEXT" -le "$FROM" ] && NEXT=$((FROM + 1))
    echo "[survey_drive] seg from=$FROM timeout/err rc=$RC last=$NEXT ($(( $(date +%s) - T0 ))s) — 再開"
    FROM=$NEXT
  fi
done
python3 "$HERE/merge_survey.py" 2>/dev/null || true
echo "[survey_drive] done (segments=$SEGS)"
