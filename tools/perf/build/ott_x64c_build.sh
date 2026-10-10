#!/usr/bin/env bash
# bit-exact な OTT (tools/ott の自作 x64c lifter 出力; 読取専用コピー) を任意最適化でビルド。
#   ott_x64c_build.sh [variants...]   既定: o0 o1 o2 o3 o2lto o3lto o3ltosimd → work/ott_x64c/<v>.cjs
# 前提: bash tools/ott/ott_e2e.sh 実行済み (tools/ott/work/lift/ott_lifted.c, ott_data.c が存在)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../flags.sh"
OTT="$HERE/../../ott"; S="$WORK/ott_x64c/src"; O="$WORK/ott_x64c"
mkdir -p "$S"
cp "$OTT/work/lift/ott_lifted.c" "$OTT/work/lift/ott_data.c" "$OTT"/rt/ott_{cpu.h,cpu.c,glue.c,ovr.c} "$S/"
declare -A F=([o0]="-O0" [o1]="-O1" [o2]="-O2" [o3]="-O3" [o2lto]="-O2 -flto" [o3lto]="-O3 -flto" [o3ltosimd]="-O3 -flto -msimd128")
b() { local n=$1; shift
  # shellcheck disable=SC2086
  emcc ${F[$n]} -ffp-contract=off -fno-fast-math -I"$S" "$S"/ott_lifted.c "$S"/ott_data.c "$S"/ott_cpu.c "$S"/ott_glue.c "$S"/ott_ovr.c \
    -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
    -sEXPORTED_FUNCTIONS=_ott_run,_ott_xmm0,_ott_set_stackarg,_ott_data_install,_ott_rget,_malloc -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
    -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) -o "$O/$n.cjs"
  echo "[x64c] $n $(stat -c %s "$O/$n.wasm") B"; }
V=("$@"); [ ${#V[@]} -eq 0 ] && V=(o0 o1 o2 o3 o2lto o3lto o3ltosimd)
for v in "${V[@]}"; do b "$v" & while [ "$(jobs -rp | wc -l)" -ge 6 ]; do wait -n; done; done; wait
