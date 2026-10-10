#!/usr/bin/env bash
# FFT ベンチ用 wasm 2 本をビルド: 旧実装 (git HEAD の src/ipp_fft.c = 倍精度基数2) と 新実装 (pffft)。
# 同一フラグ (-O2 -DNDEBUG -ffp-contract=off -fno-fast-math, EXTRA で -msimd128) で、FFT 関数のみを export する。
# usage: [EXTRA=-msimd128] bash build_bench.sh   (成果物は ../work/bench/*.wasm)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; FFT="$(dirname "$HERE")"; SHIM="$(dirname "$FFT")"; IPP="$(dirname "$SHIM")"
W="$FFT/work/bench"; mkdir -p "$W"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
git -C "$IPP/../.." show HEAD:tools/ipp/src/ipp_fft.c > "$W/ipp_fft_old.c"   # 差替え前の正確なソース (git 由来)
FLAGS="-O2 -DNDEBUG -DPFFFT_ENABLE_WASM -ffp-contract=off -fno-fast-math"
EXTRA="${EXTRA:-}"
TAG=$([ "${EXTRA:-}" != "" ] && echo _simd || echo)
OLD_EXP="['_ippsFFTGetSize_R_32f','_ippsFFTGetSize_R_64f','_ippsFFTInit_R_32f','_ippsFFTInit_R_64f','_ippsFFTFwd_RToPack_32f','_ippsFFTFwd_RToPack_32f_I','_ippsFFTFwd_RToPack_64f','_ippsFFTFwd_RToPack_64f_I','_ippsFFTInv_PackToR_32f','_ippsFFTInv_PackToR_32f_I','_ippsFFTInv_PackToR_64f','_ippsFFTInv_PackToR_64f_I','_ippsFFTFwd_RToCCS_32f_I','_ippsFFTInv_CCSToR_32f_I','_malloc','_free']"
NEW_EXP="['_ippsFFTGetSize_R_32f','_ippsFFTGetSize_R_64f','_ippsFFTInit_R_32f','_ippsFFTInit_R_64f','_ippsFFTFwd_RToPack_32f','_ippsFFTFwd_RToPack_32f_I','_ippsFFTFwd_RToPack_64f','_ippsFFTFwd_RToPack_64f_I','_ippsFFTInv_PackToR_32f','_ippsFFTInv_PackToR_32f_I','_ippsFFTInv_PackToR_64f','_ippsFFTInv_PackToR_64f_I','_ippsFFTFwd_RToCCS_32f','_ippsFFTFwd_RToCCS_32f_I','_ippsFFTFwd_RToCCS_64f','_ippsFFTFwd_RToCCS_64f_I','_ippsFFTInv_CCSToR_32f','_ippsFFTInv_CCSToR_32f_I','_ippsFFTInv_CCSToR_64f','_ippsFFTInv_CCSToR_64f_I','_ippsFFTFwd_RToPerm_32f','_ippsFFTFwd_RToPerm_32f_I','_ippsFFTFwd_RToPerm_64f','_ippsFFTFwd_RToPerm_64f_I','_ippsFFTInv_PermToR_32f','_ippsFFTInv_PermToR_32f_I','_ippsFFTInv_PermToR_64f','_ippsFFTInv_PermToR_64f_I','_malloc','_free']"
emcc $FLAGS $EXTRA -I"$IPP/src" "$W/ipp_fft_old.c" -o "$W/fft_old$TAG.wasm" \
  -sSTANDALONE_WASM=1 -sEXPORTED_FUNCTIONS="$OLD_EXP" -sINITIAL_MEMORY=33554432 -sALLOW_MEMORY_GROWTH=1 -sERROR_ON_UNDEFINED_SYMBOLS=1 -Wl,--no-entry
emcc $FLAGS $EXTRA -I"$FFT" "$FFT/ipp_fft_pffft.c" "$FFT/pffft/pffft.c" "$FFT/pffft/pffft_double.c" "$FFT/pffft/pffft_common.c" -o "$W/fft_new$TAG.wasm" \
  -sSTANDALONE_WASM=1 -sEXPORTED_FUNCTIONS="$NEW_EXP" -sINITIAL_MEMORY=33554432 -sALLOW_MEMORY_GROWTH=1 -sERROR_ON_UNDEFINED_SYMBOLS=1 -Wl,--no-entry
ls -l "$W"/*.wasm | awk '{print $9 " bytes:", $5}'
