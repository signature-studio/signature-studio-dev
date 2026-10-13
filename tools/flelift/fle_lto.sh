#!/usr/bin/env bash
# fle_lto.sh — PERF-P9 (#168) ④: flelift closure (7,018 関数) を最適化 variant 別に link し、
# wasm サイズ・emcc 所要時間を測る。fle_lift.sh の lift 産物 (work/lift) を再利用する。
#   bash tools/flelift/fle_lto.sh [o0|o2|o2lto ...]   (既定: o0 o2 o2lto)
# 出力: work/lto/<variant>.cjs / .wasm と work/lto/summary.tsv (variant, wasm_bytes, emcc_sec)
set -euo pipefail
FLE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$FLE/../shared/env.sh"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
LIFT="$FLE/work/lift"
OUT="$FLE/work/lto"
mkdir -p "$OUT/tmp"
export TMPDIR="$OUT/tmp"
[ -f "$LIFT/fle_lifted.c" ] || { echo "run fle_lift.sh first"; exit 1; }
VARS=("$@"); [ ${#VARS[@]} -eq 0 ] && VARS=(o0 o2 o2lto)
EXPORTS=_fle_run,_fle_xmm0,_fle_xmm1,_fle_rget,_fle_mget,_fle_set_stackarg,_fle_data_install,_fle_init,_fle_reset,_malloc
for v in "${VARS[@]}"; do
  case "$v" in
    o0)    OPT="-O0" ;;
    o2)    OPT="-O2" ;;
    o2lto) OPT="-O2 -flto" ;;
    *) echo "unknown variant $v"; exit 1 ;;
  esac
  T0=$(date +%s.%N)
  emcc $OPT -ffp-contract=off -fno-fast-math -I"$FLE/rt" \
    "$LIFT/fle_lifted.c" "$LIFT/fle_data.c" "$FLE/rt/fle_cpu.c" "$FLE/rt/fle_glue.c" \
    -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
    -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
    -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
    -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
    -o "$OUT/$v.cjs" > "$OUT/$v.log" 2>&1 || { tail -20 "$OUT/$v.log"; exit 1; }
  T1=$(date +%s.%N)
  SZ=$(stat -c%s "$OUT/$v.wasm")
  printf '%s\t%s\t%.1f\n' "$v" "$SZ" "$(echo "$T1 - $T0" | bc)" | tee -a "$OUT/summary.tsv"
done
