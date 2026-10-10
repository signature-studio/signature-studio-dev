#!/usr/bin/env bash
# 負の対照: 修復 pass を 1 本ずつ外した wasm が native と一致しないことを示す (差分ハーネスの検出力確認)。
set -uo pipefail
cd "$(dirname "$0")"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
build() { # $1=name $2=ll
  emcc -w -O1 -msimd128 -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=64MB -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=KhGain \
    -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry -sEXPORTED_FUNCTIONS=_function_1804b0380,_malloc,_free \
    -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32 -Wl,--no-gc-sections "$2" kh_simd_gain.c -o "work/neg_$1.cjs" 2>&1 | tail -2
  echo -n "[$1] "; node poc_gain_compare.mjs work/vectors.json "work/neg_$1.cjs" | tail -1 || true
}
KH_P1_NOFIX=1 python3 ir_kh_p1.py work/gain_lift.ll work/neg_dedup.ll >/dev/null   # declare 重複除去のみ (修復無し)
python3 ir_kh_f7.py work/neg_dedup.ll work/neg_nop1.ll >/dev/null   # f7 のみ (p1 無し)
build no_p1 work/neg_nop1.ll
build no_f7 work/gain_p1.ll                                          # p1 のみ (f7 無し)
build raw_retdec work/neg_dedup.ll                                  # 無修復
exit 0
