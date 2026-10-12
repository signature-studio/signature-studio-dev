# 本番 pthread ビルドの emcc フラグ集 (RT-2 #120 で確定。DESIGN.md §2.4 / REPORT.md 参照)。
# build_pthread.sh から source される。
#   PROD_POOL : pthread プール事前確保数 (既定 12 = tools/audio/flags.sh と同値)

PROD_CLANG_FLAGS=(
  -w
  -Wno-error=int-conversion
  -Wno-implicit-function-declaration
  -fno-strict-aliasing
  -O1
)

PROD_EMCC_FLAGS=(
  -pthread
  -sPROXY_TO_PTHREAD
  -sPTHREAD_POOL_SIZE="${PROD_POOL:-12}"
  -sALLOW_MEMORY_GROWTH=1
  -sGROWABLE_ARRAYBUFFERS=2
  -sMODULARIZE
  -sEXPORT_ES6
  -sENVIRONMENT=web,worker
  -sEXIT_RUNTIME=1
  -sERROR_ON_UNDEFINED_SYMBOLS=1
  -sEXPORTED_RUNTIME_METHODS=wasmMemory,HEAPU8
)
