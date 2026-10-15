# M1 定型フラグ集 (strategy.md §2.1 が「独立ファイル化してコミット」と指定したファイル)。
# m1.sh から source して使う。
# (#4566: e2e path filter 検証用の無変更コメント行)

# ---------------------------------------------------------------
# M1 PoC 用 emcc フラグ (toolchain_setup.md E2E-1/E2E-2 の実績値そのまま)。
# node 上で動かす PoC の検証に使用する。
# ---------------------------------------------------------------
EMCC_FLAGS_M1=(
  -w
  -Wno-error=int-conversion
  -Wno-implicit-function-declaration
  -sERROR_ON_UNDEFINED_SYMBOLS=0
)

# ---------------------------------------------------------------
# §2.1 定型フラグ (固定してコミットするもの)。
# M1 の実行パイプライン (C) 再コンパイル / (D) Emscripten ビルド で
# 本番 (M3 以降) に使う予定の値をここに確定して置いておく。
#
# CLANG_FLAGS := -w -Wno-error=int-conversion -Wno-implicit-function-declaration \
#   -fno-strict-aliasing -frounding-math -fno-fast-math \
#   -O1 -msimd128
# EMCC_FLAGS  := -sALLOW_MEMORY_GROWTH=1 -sPTHREAD_POOL_SIZE=8 \
#   -sPROXY_TO_PTHREAD=1 -sAUDIO_WORKLET=1 -sWASM_WORKERS=1 \
#   -sOFFSCREEN_FRAMEBUFFER=1 -sMAX_WEBGL_VERSION=2 -sENVIRONMENT=web,webview,worklet \
#   -sSTACK_SIZE=64MB -sSTACK_OVERFLOW_CHECK=0 \
#   -sERROR_ON_UNDEFINED_SYMBOLS=0 -sASSERTIONS=0
# ---------------------------------------------------------------
CLANG_FLAGS=(
  -w
  -Wno-error=int-conversion
  -Wno-implicit-function-declaration
  -fno-strict-aliasing
  -frounding-math
  -fno-fast-math
  -O1
  -msimd128
)

EMCC_FLAGS=(
  -sALLOW_MEMORY_GROWTH=1
  -sPTHREAD_POOL_SIZE=8
  -sPROXY_TO_PTHREAD=1
  -sAUDIO_WORKLET=1
  -sWASM_WORKERS=1
  -sOFFSCREEN_FRAMEBUFFER=1
  -sMAX_WEBGL_VERSION=2
  -sENVIRONMENT=web,webview,worklet
  -sSTACK_SIZE=64MB
  -sSTACK_OVERFLOW_CHECK=0
  -sERROR_ON_UNDEFINED_SYMBOLS=0
  -sASSERTIONS=0
)

# ---------------------------------------------------------------
# 固定バージョン (M1 検証条件 1: toolchain version 固定)。
# M1_STRICT=1 で m1.sh を実行するとこれらと一致しない場合は失敗する。
# ---------------------------------------------------------------
EMCC_VERSION_PIN="6.0.12"
RETDEC_VERSION_PIN="5.0"
MINGW_GCC_VERSION_PIN="13-win32"   # `x86_64-w64-mingw32-gcc --version` 表示名 (GCC 13 系, mingw runtime 13.2.0 ベース / Ubuntu)
