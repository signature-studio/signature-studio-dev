#!/usr/bin/env bash
# qfc_count.sh — DllMain 経路で実際に呼ばれる import の呼出し回数の計数 (T-SH-78 / #3411)。
#   qfc_boot.sh が作った lift (work/boot/lift) を使い、直接呼出し `imp_<名>();` を計数版 (`__cnt_imp_<名>`) に書き換えて emcc する。
#   戻り値・副作用は変えない (計数は stderr の "[fle] CALL <名>" のみ)。判定 (PASS/FAIL) はしない。
# 前提: qfc_boot.sh を先に 1 回実行して work/boot/lift/lift_meta.json が存在すること。env.sh の FL_WIN64_DIR 不要 (lift 済み)。
# 出力: work/count/call.log (DllMain → GetStats → CleanUp の段ごとの [fle] 行と [step]/[ret]/[trap])。
set -euo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/env.sh"
cd "$QFC"
L="$QFC/work/boot/lift"
[ -f "$L/lift_meta.json" ] || { echo "[qfc_count] lift が無い: 先に qfc_boot.sh を実行 ($L)"; exit 2; }
C="$QFC/work/count"
mkdir -p "$C"
"$QFC_PY" gen_count_wrap.py "$L/lift_meta.json" "$L/fle_lifted.c" "$C"
emcc -O0 -ffp-contract=off -fno-fast-math -I../flelift/rt "$C/fle_lifted.c" "$L/fle_data.c" "$C/count_wrap.c" \
  qfc_imp.c ../flelift/rt/fle_cpu.c ../flelift/rt/fle_glue.c \
  -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -sEXIT_RUNTIME=1 -sEXPORTED_FUNCTIONS=_fle_run,_fle_xmm0,_fle_xmm1,_fle_rget,_fle_mget,_fle_set_stackarg,_fle_data_install,_fle_init,_fle_reset,_malloc \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
  -o "$C/qfcl_count.cjs"
QFC_CJS="$C/qfcl_count.cjs" QFC_CALL_LOG="$C/call.log" node "$QFC/qfc_count.mjs" || true
cat "$C/call.log"
