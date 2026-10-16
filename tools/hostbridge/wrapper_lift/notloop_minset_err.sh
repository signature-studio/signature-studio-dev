#!/bin/bash
# #5743 (HB-H59): 1 組 (関数範囲) について、emcc -fsyntax-only の `not in loop` 件数を 0 にする
# backend 最適化の最小集合を 1-minimal で求める (notloop_minset.sh は注釈の復帰を見る)。
# 使い方 (cwd=リポジトリルート。emcc は PATH に通すこと):
#   RETDEC_BIN=<retdec>/bin/retdec-decompiler TMP=<作業dir> \
#     bash tools/hostbridge/wrapper_lift/notloop_minset_err.sh <fl-win64 PE> <lo-hi> <opts 一覧ファイル>
set -u
: "${RETDEC_BIN:?}" "${TMP:?}"
PE=$1; RANGE=$2; OPTS=$(paste -sd, "$3")
mkdir -p "$TMP"
clean() {
  timeout 100 "$RETDEC_BIN" -s -o "$TMP/e.c" --select-ranges "$RANGE" --select-decode-only \
    --backend-disabled-opts "$1" "$PE" >/dev/null 2>&1
  [ "$(timeout 100 emcc -c -fsyntax-only -w -ferror-limit=0 "$TMP/e.c" 2>&1 | grep -c 'not in loop')" = 0 ]
}
cur=$OPTS
if ! clean "$cur"; then echo "FULL_DOES_NOT_CLEAN $RANGE"; exit 1; fi
for o in $(echo "$OPTS" | tr , ' '); do
  cand=$(echo ",$cur," | sed "s/,$o,/,/; s/^,//; s/,$//")
  if clean "$cand"; then cur=$cand; fi
done
echo "MINIMAL_ERR $RANGE $cur"
