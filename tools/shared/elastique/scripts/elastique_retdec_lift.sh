#!/usr/bin/env bash
# élastique_x64.dll の .text pdata 関数を 1 関数ずつ RetDec v5.0 で lift する (T-SH-110 / #4284)。
# 使い方: RETDEC=<retdec-decompiler> bash elastique_retdec_lift.sh <dll> <ranges.txt> <outdir> [並列数]
# ranges.txt は "<begin> <end>" (16 進 VA・排他) の 1 行 1 関数。出力: <outdir>/<begin>.ll (成功)・<begin>.log (失敗)。
# 1 関数 = 1 プロセスにするのは、RetDec の decode が一部の関数で "capstone2llvmir: Should not be possible." を返すため
# (まとめて渡すと 1 関数の失敗で全体が落ちる)。
set -u
DLL=$1; RANGES=$2; OUT=$3; PAR=${4:-4}; LIFT_TIMEOUT=${LIFT_TIMEOUT:-60}
mkdir -p "$OUT"
one() {
  local b=${1%% *} e=${1##* }
  if timeout "$LIFT_TIMEOUT" "$RETDEC" "$DLL" --select-ranges "$b-$e" --select-decode-only -o "$OUT/$b.ll" > "$OUT/$b.log" 2>&1; then
    rm -f "$OUT/$b.log"; echo "$b ok"
  else
    echo "$b fail rc=$?"
  fi
}
export -f one; export RETDEC DLL OUT LIFT_TIMEOUT
xargs -P "$PAR" -L1 bash -c 'one "$0 $1"' < "$RANGES"
