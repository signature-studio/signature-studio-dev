#!/usr/bin/env bash
# lift_ranges.sh の RetDec 実行より後 (正規化 → pass 鎖 → helper 生成) を、RetDec の C バックエンドを待たずに実行する。
#   bash tools/plugins/sampler/lift_from_ll.sh <PE> <ranges> <outdir> <name> [timeout_sec]    (引数は lift_ranges.sh と同じ)
# 動機: lift_ranges.sh は RetDec の終了を待つが、C 出力 (HLL 最適化・変数名付け) は使わない。 大型 DLL ではこの段が 10 分以上・8 GiB 超
#       (RetDec の既定メモリ上限 = 搭載 RAM の半分 → "out of memory; trying to recover") になる (実測は REPORT §5)。
# 動作: <outdir>/<name>.drc.ll が無ければ lift_ranges.sh と同じ RetDec 呼出をバックグラウンドで起動し、ログに "LLVM IR -> HLL" 段が出た時点
#       (= .ll の書き出し後) で RetDec を kill する。 .ll があれば RetDec は走らせない。 その後は lift_ranges.sh の後段をそのまま実行する。
#       lift_ranges.sh 本体から切り出すので pass 鎖の二重定義にならない。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
LR="$HERE/../lift/lift_ranges.sh"
OUT="$3"; NAME="$4"; TMO="${5:-1800}"
mkdir -p "$OUT/tmp"
T="$OUT/tmp/lift_after_retdec.sh"
if [ -f "$OUT/$NAME.drc.ll" ]; then
  sed '/^\/opt\/retdec\/bin\/retdec-decompiler/,+1d' "$LR" > "$T"
  want=2
else
  sed '/^[[:space:]]*--select-ranges/ s#2>&1$#2>\&1 \&\nRDPID=$!\ntimeout "$TMO" tail -n +1 -F "$OUT/$NAME.retdec.log" 2>/dev/null | grep -m1 -q "LLVM IR -> HLL" || true\nkill -9 "$RDPID" 2>/dev/null || true\nwait "$RDPID" 2>/dev/null || true#' "$LR" > "$T"
  want=-4
fi
[ "$(( $(wc -l < "$LR") - $(wc -l < "$T") ))" = "$want" ] || { echo "[lift_from_ll] lift_ranges.sh の RetDec 呼出を特定できない" >&2; exit 1; }
sed -i "s#^HERE=.*#HERE='$(cd -- "$HERE/../lift" && pwd)'#" "$T"
exec bash "$T" "$@"
