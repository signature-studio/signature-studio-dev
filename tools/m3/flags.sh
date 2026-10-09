#!/usr/bin/env bash
# M3 定型フラグ集 (tools/m1/flags.sh の流儀を踏襲)。
# m3.sh から source して使う。全ツールバージョンを pin する。

# ---------------------------------------------------------------
# 固定バージョン (M1 検証条件 1 の継承 + M3 追加分)
# ---------------------------------------------------------------
EMCC_VERSION_PIN="6.0.12"
RETDEC_VERSION_PIN="5.0"
NODE_MAJOR_PIN="18"          # 下限
PYTHON3_MIN="3.10"
GHIDRA_VERSION_PIN="12.1.4"  # M2 との相互照合用 (M3 本パイプラインでは未使用)
emsdk_PATH="/opt/emsdk"
RETDEC_PATH="/opt/retdec"

# ---------------------------------------------------------------
# IR 正規化後の lifted IR → object/wasm 再コンパイル (M3 定型)。
# m1/flags.sh CLANG_FLAGS と同一思想。A_langA / 上位に M2 実績値を継承
# (GLOBAL_BASE=512MB: emcc runtime 領域を 0x20000000 以降へ置き、
#  lifted IR の x64 アドレス空間 (VA==offset, < 2^32) と非衝突にする)。
# ---------------------------------------------------------------
M3_CLANG_LL_FLAGS=(          # IR 入力 → object
  -O1                        # §2.1 定型 (mem2reg/SROA は clang パイプライン側でも効く)
  -msimd128
  -Wno-error=implicit-function-declaration
  -w
)

M3_EMCC_COMMON=(             # §2.1 EMCC_FLAGS の node 検証用縮小集合
  -sALLOW_MEMORY_GROWTH=1
  -sSTACK_SIZE=8MB           # Delphi closure 関数の深い stack 用に M2 実績 (1MB) から引き上げ
  -sGLOBAL_BASE=536870912    # 512MB = M2 PoC (poc_crc8_wasm.sh) 実績の継承
  -sENVIRONMENT=node
  -sMODULARIZE=1
  -sEXPORT_NAME=createModule
  -sERROR_ON_UNDEFINED_SYMBOLS=0
  -sEXIT_RUNTIME=1           # fail-fast abort の exit コード伝播
  --no-entry
  -Wl,--no-gc-sections       # --no-entry 構成で EXPORTED_FUNCTIONS が tree-sweep されないように
)

# -O0 入口版 (lift-down pass 効果の定量化用: backend 最適化を切った比較ベース)
M3_EMCC_O0=( "${M3_EMCC_COMMON[@]}" -O0 )

# 本番相当 (§2.1 定型 O1 潰し済み / M3_IR 変換後のリンク)
M3_EMCC_O1=( "${M3_EMCC_COMMON[@]}" -O1 )
