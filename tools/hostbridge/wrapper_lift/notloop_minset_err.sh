#!/bin/bash
# #5743 (HB-H59): 1 組 (関数範囲) について、emcc -fsyntax-only の `not in loop` 件数を 0 にする
# backend 最適化の最小集合を 1-minimal で求める (notloop_minset.sh は注釈の復帰を見る)。
# 件数は「RetDec が成功し e.c が生成され、emcc が実行できた」ときだけ数える。失敗時は中止する。
# 使い方 (cwd=リポジトリルート。emcc は PATH に通すこと):
#   RETDEC_BIN=<retdec>/bin/retdec-decompiler TMP=<作業dir> \
#     bash tools/hostbridge/wrapper_lift/notloop_minset_err.sh <fl-win64 PE> <lo-hi> <opts 一覧ファイル>
set -u
: "${RETDEC_BIN:?}" "${TMP:?}"
command -v emcc >/dev/null || { echo "EMCC_NOT_ON_PATH" >&2; exit 2; }
PE=$1; RANGE=$2; OPTS=$(paste -sd, "$3")
mkdir -p "$TMP"
N=-1
# $1: --backend-disabled-opts の値 (空なら指定しない)。成功時 N に件数を入れる。
notloop() {
  local args=()
  [ -n "$1" ] && args=(--backend-disabled-opts "$1")
  N=-1
  rm -f "$TMP/e.c"
  timeout 100 "$RETDEC_BIN" -s -o "$TMP/e.c" --select-ranges "$RANGE" --select-decode-only \
    "${args[@]}" "$PE" >/dev/null 2>&1 || return 1
  [ -s "$TMP/e.c" ] || return 1
  local out rc
  out=$(timeout 100 emcc -c -fsyntax-only -w -ferror-limit=0 "$TMP/e.c" 2>&1); rc=$?
  # clang の構文エラーは rc=1 で、C の未解決 identifier 等で普通に出る。rc>=2・timeout・ファイル無しは失敗。
  if [ "$rc" -gt 1 ] || grep -q 'no such file' <<<"$out"; then return 1; fi
  N=$(grep -c 'not in loop' <<<"$out" || true)
}
must() { notloop "$1" || { echo "TOOL_FAILED (disabled='$1') $RANGE" >&2; exit 2; }; }
must ""
if [ "$N" = 0 ]; then echo "POSITIVE_CONTROL_FAILED: 既定 C に not in loop が無い $RANGE"; exit 1; fi
cur=$OPTS
must "$cur"
if [ "$N" != 0 ]; then echo "FULL_DOES_NOT_CLEAN $RANGE"; exit 1; fi
for o in $(echo "$OPTS" | tr , ' '); do
  cand=$(echo ",$cur," | sed "s/,$o,/,/; s/^,//; s/,$//")
  must "$cand"
  if [ "$N" = 0 ]; then cur=$cand; fi
done
echo "MINIMAL_ERR $RANGE $cur"
