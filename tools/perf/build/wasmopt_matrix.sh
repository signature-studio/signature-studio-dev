#!/usr/bin/env bash
# wasm-opt (binaryen) 水準比較: clang 側 -O2/-O3 のみで binaryen を通していない *raw* wasm を入力に、
# 各 wasm-opt 構成を適用して work/ott/wo_<input>_<name>/ を作る (glue は raw のものを流用)。
# 出力: work/wasmopt_times.tsv (name, wasm-opt 秒, bytes)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../flags.sh"
WO=/opt/emsdk/upstream/bin/wasm-opt
declare -A F
F[none]=""                               # raw (binaryen 無し)
F[O1]="-O1"
F[O2]="-O2"
F[O3]="-O3"
F[Os]="-Os"
F[Oz]="-Oz"
F[O4]="-O4"
F[O2conv]="-O2 --converge"
F[O3conv]="-O3 --converge"
F[O3convfl]="--flatten --rereloop -O3 --converge"   # 重い: 関数単位の再構成
ORDER=(none O1 O2 O3 Os Oz O4 O2conv O3conv O3convfl)
: > "$WORK/wasmopt_times.tsv"
for in in o2raw o3raw o2rawsimd; do
  for n in "${ORDER[@]}"; do
    d="$WORK/ott/wo_${in}_$n"; rm -rf "$d"; mkdir -p "$d"
    cp "$WORK/ott/$in/ott.mjs" "$d/"
    s=$(date +%s.%N)
    if [ "$n" = none ]; then cp "$WORK/ott/$in/ott.wasm" "$d/ott.wasm"; rc=0
    else $WO "$WORK/ott/$in/ott.wasm" ${F[$n]} --enable-sign-ext --enable-mutable-globals --enable-nontrapping-float-to-int --enable-bulk-memory --enable-bulk-memory-opt --enable-multivalue --enable-reference-types --enable-simd -o "$d/ott.wasm" 2>"$d/wo.log"; rc=$?; fi
    e=$(date +%s.%N)
    printf 'wo_%s_%s\t%s\t%.2f\t%s\n' "$in" "$n" "$rc" "$(echo "$e - $s" | bc)" "$(stat -c %s "$d/ott.wasm")" | tee -a "$WORK/wasmopt_times.tsv"
  done
done
