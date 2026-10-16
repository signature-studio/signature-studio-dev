#!/bin/bash
# #5743 (HB-H59): 1 組 (関数範囲, 飛び先 VA) について、飛び先の注釈 `// <VA>` を戻す
# backend 最適化の最小集合を 1-minimal で求める。全 disable で戻ることを前提とする。
# 使い方 (cwd=リポジトリルート):
#   RETDEC_BIN=<retdec>/bin/retdec-decompiler TMP=<作業dir> \
#     bash tools/hostbridge/wrapper_lift/notloop_minset.sh <fl-win64 PE> <lo-hi> <飛び先 VA> <opts 一覧ファイル>
# opts 一覧ファイル: 1 行 1 名 (例: BitOpToLogOpOptimizer)。RetDec のヘッダ名 (retdec/llvmir2hll/optimizer/optimizers/*.h) から作る。
set -u
: "${RETDEC_BIN:?}" "${TMP:?}"
PE=$1; RANGE=$2; T=$3; OPTS=$(paste -sd, "$4")
mkdir -p "$TMP"
restores() {
  timeout 100 "$RETDEC_BIN" -s -o "$TMP/minset.c" --select-ranges "$RANGE" --select-decode-only \
    --backend-disabled-opts "$1" "$PE" >/dev/null 2>&1
  [ "$(grep -c "^\s*// $T\s*\$" "$TMP/minset.c" 2>/dev/null)" = 1 ]
}
cur=$OPTS
if ! restores "$cur"; then echo "FULL_DOES_NOT_RESTORE $RANGE $T"; exit 1; fi
for o in $(echo "$OPTS" | tr , ' '); do
  cand=$(echo ",$cur," | sed "s/,$o,/,/; s/^,//; s/,$//")
  if restores "$cand"; then cur=$cand; fi
done
echo "MINIMAL $RANGE $T $cur"
