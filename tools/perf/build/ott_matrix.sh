#!/usr/bin/env bash
# OTT 最適化マトリクス全ビルド → work/ott/<variant>/ + results/ott_sizes.json
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../flags.sh"
B="$HERE/ott_build.sh"
SIMD="-msimd128"
declare -A V   # name → build args
V[o0]="--opt -O0 --gc 0 --exports full"                    # M10 現行設定の再現 (no-simd, no-gc, 全 export)
V[o0min]="--opt -O0"
V[o1]="--opt -O1"
V[o2]="--opt -O2"
V[o3]="--opt -O3"
V[os]="--opt -Os"
V[oz]="--opt -Oz"
V[o0simd]="--opt -O0 --cflags $SIMD --ldflags $SIMD"
V[o1simd]="--opt -O1 --cflags $SIMD --ldflags $SIMD"
V[o2simd]="--opt -O2 --cflags $SIMD --ldflags $SIMD"
V[o3simd]="--opt -O3 --cflags $SIMD --ldflags $SIMD"
V[ossimd]="--opt -Os --cflags $SIMD --ldflags $SIMD"
V[o2lto]="--opt -O2 --lto 1"
V[o3lto]="--opt -O3 --lto 1"
V[o2ltosimd]="--opt -O2 --lto 1 --cflags $SIMD --ldflags $SIMD"
V[o3ltosimd]="--opt -O3 --lto 1 --cflags $SIMD --ldflags $SIMD"
V[oslto]="--opt -Os --lto 1"
V[o2thinlto]="--opt -O2 --cflags -flto=thin --ldflags -flto=thin"
V[o3thinlto]="--opt -O3 --cflags -flto=thin --ldflags -flto=thin"
V[o3lto_m1flags]="--opt -O3 --lto 1 --cflags '-fno-strict-aliasing -frounding-math -fno-fast-math'"
V[o3lto_wasmopt]="--opt -O3 --lto 1 --ldflags -Wl,--lto-O3"
V[o2fullnogc]="--opt -O2 --exports full --gc 0"
V[o2fullgc]="--opt -O2 --exports full --gc 1"
V[o2m1flags]="--opt -O2 --cflags '-fno-strict-aliasing -frounding-math -fno-fast-math'"
V[o2thr]="--opt -O2 --pthread 1"
V[o2thrsimd]="--opt -O2 --pthread 1 --cflags $SIMD --ldflags $SIMD"
V[o2raw]="--opt -O2 --link-opt -O0"                        # clang -O2 のみ / binaryen 無し (wasm-opt マトリクスの入力)
V[o3raw]="--opt -O3 --link-opt -O0"
V[o2rawsimd]="--opt -O2 --link-opt -O0 --cflags $SIMD --ldflags $SIMD"
ORDER=(o3ltosimd oslto o2thinlto o3thinlto o3lto_m1flags o3lto_wasmopt o0 o0min o1 o2 o3 os oz o0simd o1simd o2simd o3simd ossimd o2lto o3lto o2ltosimd o2fullnogc o2fullgc o2m1flags o2thr o2thrsimd o2raw o3raw o2rawsimd)
[ $# -gt 0 ] && ORDER=("$@")
mkdir -p "$RESULTS"
for n in "${ORDER[@]}"; do
  s=$(date +%s.%N)
  eval "bash $B $n ${V[$n]}" > "$WORK/ott_build_$n.log" 2>&1 && st=ok || st=FAIL
  e=$(date +%s.%N)
  printf '%s\t%s\t%.1f\t%s\n' "$n" "$st" "$(echo "$e - $s" | bc)" "$(stat -c %s "$WORK/ott/$n/ott.wasm" 2>/dev/null || echo 0)" | tee -a "$WORK/ott_matrix_times.tsv"
done
