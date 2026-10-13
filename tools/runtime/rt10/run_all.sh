#!/usr/bin/env bash
# run_all.sh — RT-10 (#128) 1 コマンド再現: 実 FLEngine lift の build → サイズ/圧縮 → Chrome 計測一式。
#   bash tools/runtime/rt10/run_all.sh [--skip-build] [--soak-sec 180]
# 素材: FL_WIN64_DIR (fl-win64 展開先), /opt/emsdk。build は RAM 16GB + swap 追加が必要 (REPORT 参照)。
# 結果: tools/runtime/rt10/results/rt10_*.jsonl (追記。再実行前に消すこと)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
SOAK=180; BUILD=1
while [ $# -gt 0 ]; do case "$1" in --skip-build) BUILD=0;; --soak-sec) SOAK="$2"; shift;; esac; shift; done
[ "$BUILD" = 1 ] && bash "$HERE/build_fle_boot.sh"
M="node $HERE/measure.mjs"
[ -f "$HERE/../../flelift/work/boot/web/fleweb.wasm.br" ] || $M sizes   # brotli q11 は約 286 s かかるため .br があれば再利用
$M cold  --reps 3 --flags default,eager,liftoff,notier --mode stream
$M cold  --reps 3 --flags default --mode bytes
$M warm  --reps 3 --flags default
$M bw    --reps 3 --mbps 10,50,100,1000 --flags default --mode stream
$M tier  --reps 3 --boots 6 --flags default,liftoff,notier
$M soak  --sec "$SOAK" --flags default
