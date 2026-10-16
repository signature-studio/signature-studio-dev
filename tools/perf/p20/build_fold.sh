#!/usr/bin/env bash
# P23 (#3680): Fresh Air (build_fa_renamed.sh の fa_ 改名済み TU) と OTT (tools/ott の lift 産物) を 1 link の 1 wasm (= 1 Memory) にする。
#   usage: bash tools/perf/p20/build_fold.sh      (前提: build_fa_renamed.sh の出力 work/fa2、tools/ott/work/lift、tools/ott/rt)
#   出力: tools/perf/p20/work/fold/fold.cjs・fold.wasm (gitignore の work/。commit しない)
#   署名: node tools/perf/p20/fold_sig.mjs tools/perf/p20/work/fold/fold.cjs  (単独基準: FA 5e5287b5 / OTT 6b1696f0)
#   OTT は ref (-O0) 版の flags で作る (署名の基準と同じ)。FA は build_fa_renamed.sh と同じ flags。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../../.." && pwd)"
FA2="$HERE/work/fa2"
OTT="$ROOT/tools/ott"
OUT="$HERE/work/fold"
OBJ="$OUT/obj"
mkdir -p "$OBJ"
[ -f "$FA2/rt/fle_lifted.c" ] || { echo "[build_fold] FA の改名版が無い: bash tools/perf/p20/build_fa_renamed.sh を先に" >&2; exit 2; }
[ -f "$OTT/work/lift/ott_lifted.c" ] || { echo "[build_fold] OTT の lift 産物が無い: tools/ott/work/lift (work-m6-ott 素材)" >&2; exit 2; }
if ! command -v emcc >/dev/null 2>&1; then source "${EMSDK:-/opt/emsdk}/emsdk_env.sh" >/dev/null 2>&1; fi
FA_FLAGS="-O0 -ffp-contract=off -fno-fast-math"
RENAME="-include $FA2/rt/fa_rename.h"
for tu in fle_lifted fle_data fle_cpu fle_glue; do
  emcc -c $FA_FLAGS $RENAME -w -I "$FA2/rt" "$FA2/rt/$tu.c" -o "$OBJ/fa_$tu.o"
done
for f in "$OTT/work/lift/ott_lifted.c" "$OTT/work/lift/ott_data.c" "$OTT/rt/ott_cpu.c" "$OTT/rt/ott_glue.c" "$OTT/rt/ott_ovr.c"; do
  emcc -c $FA_FLAGS -w -I "$OTT/rt" "$f" -o "$OBJ/ott_$(basename "${f%.c}").o"
done
EXPORTS=_fle_run,_fle_xmm0,_fle_xmm1,_fle_rget,_fle_mget,_fle_set_stackarg,_fle_data_install,_fle_init,_fle_reset,_ott_run,_ott_xmm0,_ott_set_stackarg,_ott_data_install,_ott_rget,_ott_set_gbase,_malloc
emcc $FA_FLAGS "$OBJ"/*.o \
  -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) -Wl,--no-gc-sections -o "$OUT/fold.cjs" > "$OUT/link.log" 2>&1 \
  || { echo "[build_fold] link 失敗: $OUT/link.log" >&2; tail -20 "$OUT/link.log" >&2; exit 3; }
ls -la "$OUT/fold.wasm" | awk '{print "wasm bytes:", $5}'
