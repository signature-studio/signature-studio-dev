# M4 shim ビルド用 emcc フラグ集 (tools/m1/flags.sh の流儀を踏襲)。
# - CLANG_FLAGS / 本番 EMCC_FLAGS は strategy.md §2.1 定型を共通参照 (tools/m1/flags.sh)。
#   shim は自前 C で書くため基本 O1 + 定型系のみ使用。
# - SHIM_EMCC_ST : シングルスレッド (検証用 smoke + fail-fast 実確認)
# - SHIM_EMCC_MT : pthread (本番相当。node 上でワーカー複数動作を検証)

SHIM_CLANG_FLAGS=(
  -w
  -Wno-error=int-conversion
  -Wno-implicit-function-declaration
  -fno-strict-aliasing
  -O1
)

# 共通 (ST/MT とも): node 実行前提。EXIT_RUNTIME=1 は exit コード伝播のため必須。
# EXPORTED_FUNCTIONS は exports.txt をそのまま使う (main は test.sh が
# build/install_exports.txt に追加して参照する — exports.txt は実運用ライブラリ
# 相当に保つため main を含めない)。
SHIM_EMCC_COMMON=(
  -sALLOW_MEMORY_GROWTH=1
  -sEXPORTED_FUNCTIONS=@"$SHIM_RUN_EXPORTS"
  -sERROR_ON_UNDEFINED_SYMBOLS=1
  -sEXIT_RUNTIME=1
  -sENVIRONMENT=node
)

SHIM_EMCC_ST=( "${SHIM_EMCC_COMMON[@]}" )

SHIM_EMCC_MT=(
  "${SHIM_EMCC_COMMON[@]}"
  -pthread
  -sPTHREAD_POOL_SIZE=8
  -sPROXY_TO_PTHREAD=0
)
