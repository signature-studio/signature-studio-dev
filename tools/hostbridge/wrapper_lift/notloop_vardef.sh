#!/bin/bash
# #5743 (HB-H59): 組ごとに、VarDefStmtOptimizer だけを disable した C の (a) 注釈の有無
# (b) emcc -fsyntax-only の `not in loop` 件数を、既定 C と並べて出す。
# 注釈が戻っても件数が減らなければ、その段は break の構造エラーの原因ではない。
# 入力 $TMP/targets.txt: 行ごとに "<lo>-<hi> <飛び先 VA>" (例: 0x408770-0x4087f3 0x4087ba)。
# 使い方 (cwd=リポジトリルート。emcc は PATH に通すこと):
#   RETDEC_BIN=<retdec>/bin/retdec-decompiler TMP=<作業dir> \
#     bash tools/hostbridge/wrapper_lift/notloop_vardef.sh <fl-win64 PE>
set -u
: "${RETDEC_BIN:?}" "${TMP:?}"
PE=$1
while read -r rng t; do
  tag=$(echo "$rng" | tr -d '-')
  timeout 100 "$RETDEC_BIN" -s -o "$TMP/vd_$tag.c" --select-ranges "$rng" --select-decode-only \
    --backend-disabled-opts VarDefStmtOptimizer "$PE" >/dev/null 2>&1
  timeout 100 "$RETDEC_BIN" -s -o "$TMP/df_$tag.c" --select-ranges "$rng" --select-decode-only "$PE" >/dev/null 2>&1
  a=$(grep -c "^\s*// $t\s*\$" "$TMP/vd_$tag.c" 2>/dev/null)
  ev=$(timeout 100 emcc -c -fsyntax-only -w -ferror-limit=0 "$TMP/vd_$tag.c" 2>&1 | grep -c "not in loop")
  ed=$(timeout 100 emcc -c -fsyntax-only -w -ferror-limit=0 "$TMP/df_$tag.c" 2>&1 | grep -c "not in loop")
  echo "$rng $t vardef_annot=${a:-0} vardef_notinloop=$ev default_notinloop=$ed"
done < "$TMP/targets.txt"
