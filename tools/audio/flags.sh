# tools/audio ビルド用 emcc フラグ (tools/m1/flags.sh, tools/shim/flags.sh の流儀を踏襲)。
# 本番 EMCC_FLAGS (tools/m1/flags.sh) と同じ pthread 系: -pthread / PROXY_TO_PTHREAD=1 / ALLOW_MEMORY_GROWTH。
# AUDIO_WORKLET / WASM_WORKERS / WebGL は本 shim では不要 (worklet は fl-audio-worklet.js が SAB を直接読む)。

FLA_CLANG_FLAGS=(
  -Wall -Wextra -Wno-unused-parameter
  -O2
  -fno-strict-aliasing
)

FLA_EMCC_FLAGS=(
  -pthread
  -sPROXY_TO_PTHREAD=1
  -sPTHREAD_POOL_SIZE=12
  -sALLOW_MEMORY_GROWTH=1
  -sINITIAL_MEMORY=67108864
  -sENVIRONMENT=web,worker
  -sERROR_ON_UNDEFINED_SYMBOLS=1
  -sSTACK_SIZE=1048576
  -sASSERTIONS=1
  -Wno-pthreads-mem-growth
  -sEXPORTED_FUNCTIONS=_main,_fla_ctl_ptr,_fla_layout_count,_fla_layout_off,_fla_layout_name,_fla_test_done_ptr,_fla_test_result_ptr
  -sEXPORTED_RUNTIME_METHODS=wasmMemory,UTF8ToString
)
