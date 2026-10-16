#!/bin/bash
# #5743 (HB-H59): notloop_probe.py の未解決 19 組について、飛び先の注釈 `// 0x<VA>` が
# 既定の backend 最適化のどの段で消えるかを測る (1 組 × 5 variant の単一 range 再 lift)。
# 使い方 (cwd=リポジトリルート):
#   RETDEC=<retdec>/bin/retdec-decompiler FL_WIN64_DIR=<fl-win64 展開先>/extracted OUT=<作業dir> \
#     bash tools/hostbridge/wrapper_lift/notloop_passes.sh <pairs.txt>
# pairs.txt: 行ごとに "<関数 lo>-<hi> <飛び先 VA> <命令>" (notloop_probe.py の出力から作る)。
# 出力: $OUT/cmp/<lo>_<target>.<variant>.c と、標準出力に "<組> <variant> <注釈の行数>"。
set -u
: "${RETDEC:?}" "${FL_WIN64_DIR:?}" "${OUT:?}"
PE="$FL_WIN64_DIR/block19091_PE.bin"
mkdir -p "$OUT/cmp"
while read -r f t _; do
  tag="${f%-*}_${t}"
  tag="${tag//0x/}"
  for v in default noopt dis_empty dis_wtwc dis_both; do
    case $v in
      default) o=() ;;
      noopt) o=(--backend-no-opts) ;;
      dis_empty) o=(--backend-disabled-opts EmptyStmtOptimizer) ;;
      dis_wtwc) o=(--backend-disabled-opts WhileTrueToWhileCondOptimizer) ;;
      dis_both) o=(--backend-disabled-opts EmptyStmtOptimizer,WhileTrueToWhileCondOptimizer) ;;
    esac
    timeout 280 "$RETDEC" -s -o "$OUT/cmp/$tag.$v.c" --select-ranges "$f" --select-decode-only "${o[@]}" "$PE" >/dev/null 2>&1
    n=$(grep -c "^\s*// $t\s*\$" "$OUT/cmp/$tag.$v.c" 2>/dev/null)
    echo "$tag $v ${n:-0}"
  done
done < "$1"
