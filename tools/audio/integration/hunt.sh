#!/usr/bin/env bash
# AU-15 (#863) 断続失敗の捕獲。e2e.sh を繰り返し、最初の FAIL で止めて位置情報つきログを残す (PASS の間は続行)。
#   bash tools/audio/integration/hunt.sh [最大回数=300] [時間上限秒=1500]
# 出力 (tools/audio/work/hunt/・gitignore): summary.txt = run ごとの結果 / fail_<n>.log = 失敗 run の e2e 全出力 (ビルド段を含む)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../../.." && pwd)"
MAX="${1:-300}"; BUDGET="${2:-1500}"
OUT="$ROOT/tools/audio/work/hunt"; mkdir -p "$OUT"
SUM="$OUT/summary.txt"; : > "$SUM"
LAST="$OUT/last.log"
start=$(date +%s); pass=0
for ((i = 1; i <= MAX; i++)); do
  if (( $(date +%s) - start >= BUDGET )); then echo "[hunt] 時間上限 ${BUDGET}s 到達: PASS ${pass} run / FAIL 0" | tee -a "$SUM"; exit 0; fi
  t=$(date +%s)
  # run ごとの全出力 (ビルド段を含む) を受ける。e2e.sh の tee は検査段に入ってからしか書かれないため、前 run のログを使わない
  bash "$HERE/e2e.sh" > "$LAST" 2>&1; rc=$?
  wall=$(( $(date +%s) - t )); load=$(cut -d' ' -f1 /proc/loadavg)
  if [ "$rc" -eq 0 ]; then
    pass=$((pass + 1))
    check=$(grep -oE '[0-9]+/[0-9]+ PASS' "$LAST" | tail -n 1)
    echo "run $i PASS exit=0 wall=${wall}s load=${load} check=${check:-none}" >> "$SUM"
  else
    if ! mv "$LAST" "$OUT/fail_$i.log"; then
      echo "run $i FAIL exit=${rc} wall=${wall}s load=${load} ログ保存失敗 ($LAST -> fail_$i.log)" | tee -a "$SUM"; exit 1
    fi
    echo "run $i FAIL exit=${rc} wall=${wall}s load=${load} log=$OUT/fail_$i.log" | tee -a "$SUM"
    grep -E '^FAIL ' "$OUT/fail_$i.log" | tee -a "$SUM"
    echo "[hunt] FAIL を捕獲 (直前までの PASS ${pass} run)" | tee -a "$SUM"
    exit 1
  fi
done
echo "[hunt] 回数上限 ${MAX} 到達: PASS ${pass} run / FAIL 0" | tee -a "$SUM"
