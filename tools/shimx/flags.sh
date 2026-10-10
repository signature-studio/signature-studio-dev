# shimx ビルド用 emcc フラグ集 (tools/shim/flags.sh の流儀を踏襲)。
# - SHIMX_CLANG_FLAGS : 共通 (shim は自前 C。lifter 生成物とは別)。int-conversion は M4 同様 warning 扱い
# - SHIMX_EMCC_ST     : シングルスレッド (smoke / fail-fast 確認)
# - SHIMX_EMCC_MT     : pthread (本番相当)
# - GLOBAL_BASE       : 64KB 以上にする。Win32 の「序数 / MAKEINTRESOURCE / 単一文字 CharUpper」は
#                       ポインタ値 < 0x10000 を整数とみなすため、静的データがそこに置かれると誤判定する
#                       (lifted ビルドは m6=0x10000000 / m11=0x10000000 で問題なし)。

SHIMX_CLANG_FLAGS=(
  -w
  -Wno-error=int-conversion
  -Wno-implicit-function-declaration
  -fno-strict-aliasing
  -O1
)

SHIMX_EMCC_COMMON=(
  -sALLOW_MEMORY_GROWTH=1
  -sERROR_ON_UNDEFINED_SYMBOLS=1
  -sEXIT_RUNTIME=1
  -sENVIRONMENT=node
  -sGLOBAL_BASE=1048576
)

SHIMX_EMCC_ST=( "${SHIMX_EMCC_COMMON[@]}" )

SHIMX_EMCC_MT=(
  "${SHIMX_EMCC_COMMON[@]}"
  -pthread
  -sPTHREAD_POOL_SIZE=12
  -sPROXY_TO_PTHREAD=0
)
