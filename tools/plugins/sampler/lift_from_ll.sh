#!/usr/bin/env bash
# lift_ranges.sh の RetDec 実行より後 (正規化 → pass 鎖 → helper 生成) だけを、既存の <outdir>/<name>.drc.ll に対して実行する。
#   bash tools/plugins/sampler/lift_from_ll.sh <PE> <ranges> <outdir> <name> [timeout_sec]    (引数は lift_ranges.sh と同じ)
# 用途: RetDec の C バックエンド (HLL 最適化・変数名付け) が .ll 出力後に 10 分以上かかり 8 GiB 超を使う大型 DLL で、
#       C は使わないので .ll が出た時点で RetDec を止めて後段だけ再開する。 pass 鎖は lift_ranges.sh 本体から切り出すので二重定義にならない。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
LR="$HERE/../lift/lift_ranges.sh"
OUT="$3"; NAME="$4"
[ -f "$OUT/$NAME.drc.ll" ] || { echo "[lift_from_ll] $OUT/$NAME.drc.ll が無い" >&2; exit 1; }
mkdir -p "$OUT/tmp"
T="$OUT/tmp/lift_after_retdec.sh"
sed '/^\/opt\/retdec\/bin\/retdec-decompiler/,+1d' "$LR" > "$T"
[ "$(( $(wc -l < "$LR") - $(wc -l < "$T") ))" = 2 ] || { echo "[lift_from_ll] lift_ranges.sh の RetDec 呼出 2 行を特定できない" >&2; exit 1; }
sed -i "s#^HERE=.*#HERE='$(cd -- "$HERE/../lift" && pwd)'#" "$T"
exec bash "$T" "$@"
