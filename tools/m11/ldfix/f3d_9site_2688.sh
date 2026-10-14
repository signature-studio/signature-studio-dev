#!/usr/bin/env bash
# f3d_9site_2688.sh — #2688 (LD-123) spill 宛 判定不能 9 site のうち上流 xor 0 の 4 site を、F3d 適用 IR で再検証する (REPORT_2688.md §3)。
# 出力: $OUT/base・$OUT/f3d の site ダンプ、$OUT/ir_reach.txt (到達性)、$OUT/targets_f3d.txt (対象ブロックの抜粋)。
# 使い方: bash tools/m11/ldfix/f3d_9site_2688.sh     環境変数: M11_WORK (既定 tools/m11/work) / FL_WIN64_DIR (既定 $RUNNER_TEMP/fl-win64) / OUT / PY
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
PE="${FL_WIN64_DIR:-${RUNNER_TEMP:-/tmp}/fl-win64}/extracted/block00031_PE.bin"
OUT="${OUT:-${RUNNER_TEMP:-/tmp}/f3d_9site_2688}"
PY="${PY:-python3}"
IMG="$W/m11_image.bin"; CFG="$W/boot*.drc.config.json"; IR="$W/boot_final3.ll"
mkdir -p "$OUT"

"$PY" "$HERE/audit_lsf_ssa.py" "$IR" "$IMG" "$CFG" --json "$OUT/ssa.json" > /dev/null
"$PY" "$HERE/ldfix.py" "$IR" "$OUT/f3d.ll" --pe "$PE" --passes f3d --only 45b170,45d0a0,45f560 --report "$OUT/f3d.json"
"$PY" "$HERE/site_dump.py" "$IR" "$IMG" "$CFG" "$OUT/ssa.json" "$OUT/base" 45d0a0,45b170,45f560
"$PY" "$HERE/site_dump.py" "$OUT/f3d.ll" "$IMG" "$CFG" "$OUT/ssa.json" "$OUT/f3d" 45d0a0,45b170,45f560

# TARGET と死んだ辺 (作者の前提。ir_reach_2660.py は辺の成立を検査しない)
R="$HERE/ir_reach_2660.py"
{
  for d in base f3d; do
    f="$OUT/$d"
    echo "[$d] 45d570 (45d0a0)"
    python3 "$R" "$f/45d0a0.txt" dec_label_pc_45d565
    python3 "$R" "$f/45d0a0.txt" dec_label_pc_45d565 dec_label_pc_45d381:dec_label_pc_45d38e
    echo "[$d] 45d581 (45d0a0)"
    python3 "$R" "$f/45d0a0.txt" dec_label_pc_45d576
    python3 "$R" "$f/45d0a0.txt" dec_label_pc_45d576 dec_label_pc_45d381:dec_label_pc_45d38e
    echo "[$d] 45b1bf (45b170)"
    python3 "$R" "$f/45b170.txt" dec_label_pc_45b1b8
    python3 "$R" "$f/45b170.txt" dec_label_pc_45b1b8 dec_label_pc_45b1a1:dec_label_pc_45b1b1
    echo "[$d] 45f938 (45f560)"
    python3 "$R" "$f/45f560.txt" dec_label_pc_45f931
    python3 "$R" "$f/45f560.txt" dec_label_pc_45f931 dec_label_pc_45f84c:dec_label_pc_45f931
  done
} > "$OUT/ir_reach.txt"
cat "$OUT/ir_reach.txt"

# 対象ブロック (store の元と消費者の join) の抜粋。機械語の対応は REPORT_2688.md §3 の表
{
  for spec in 45d0a0:dec_label_pc_45d381 45d0a0:dec_label_pc_45d565 45d0a0:dec_label_pc_45d576 45b170:dec_label_pc_45b1a1 45b170:dec_label_pc_45b1b8 45f560:dec_label_pc_45f84c 45f560:dec_label_pc_45f931; do
    fn="${spec%%:*}"; blk="${spec#*:}"
    echo "== f3d $fn $blk"
    sed -n '/^## IR/,$p' "$OUT/f3d/$fn.txt" | awk -v b="$blk:" 'index($0, b)==1 {p=1} p && /^$/ {exit} p'
  done
} > "$OUT/targets_f3d.txt"
echo "[f3d_9site_2688] wrote $OUT/ir_reach.txt $OUT/targets_f3d.txt"
