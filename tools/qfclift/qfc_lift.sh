#!/usr/bin/env bash
# qfc_lift.sh — QuickFontCache_x64.dll の lift → emcc wasm 生成 (qfc_e2e.sh / qfc_boot.sh が source する)。
# 前提: env.sh を source 済み (QFC・QFC_PE・QFC_PY)。cwd = $QFC。
#   lift_build <out-dir> <QFC_NEGCTL>            : lift + fle_data + wasm ($out/qfcl.cjs)
#     boot 用の任意設定 (未設定なら e2e と同一): QFC_ENTRIES=<entries.json> / QFC_OVERRIDE=<VA=CNAME> / QFC_EXTRA_C=<extra.c ...>
#   wasm_build <out-dir> <cjs> [extra.c ...]      : fle_lifted.c + fle_data.c (+ extra.c ...) を emcc (boot の soft stub 版に使う)
lift_build() {
  local out="$1"; mkdir -p "$out"
  "$QFC_PY" gen_entries.py "$QFC_PE" "$out/entries.json" >/dev/null
  local ov=()
  [ -n "${QFC_OVERRIDE:-}" ] && ov=(--override "$QFC_OVERRIDE")
  QFC_NEGCTL="$2" "$QFC_PY" x64c_qfc.py --pe "$QFC_PE" --entries "${QFC_ENTRIES:-$out/entries.json}" --out "$out" --closure 0 \
    --img 0x400000 --shift 0 --img-size 0x20e000 --impbase 0x1D80000 "${ov[@]}" | tail -1 | tee "$out/lift.log"
  "$QFC_PY" ../flelift/fle_data_gen.py "$QFC_PE" "$out/fle_data.c" "$out/lift_meta.json" >/dev/null
  wasm_build "$out" "$out/qfcl.cjs" ${QFC_EXTRA_C:-}
}
wasm_build() {
  local out="$1" cjs="$2"; shift 2
  emcc -O0 -ffp-contract=off -fno-fast-math -I../flelift/rt -I../shared/oss/freetype -I"$FT_SRC_INC" "$out/fle_lifted.c" "$out/fle_data.c" "$@" \
    ../shared/oss/freetype/qfc_import.c "$FT_WASM32_LIB" \
    ../flelift/rt/fle_cpu.c ../flelift/rt/fle_glue.c \
    -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
    -sEXIT_RUNTIME=1 -sEXPORTED_FUNCTIONS=_fle_run,_fle_xmm0,_fle_xmm1,_fle_rget,_fle_mget,_fle_set_stackarg,_fle_data_install,_fle_init,_fle_reset,_malloc \
    -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
    -o "$cjs" 2>&1 | tail -5
}
