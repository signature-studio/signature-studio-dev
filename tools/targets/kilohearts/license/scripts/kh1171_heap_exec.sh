#!/bin/bash
# kh1171_heap_exec.sh <build_dir> — lic_build の生成物 (final.ll/simd.c/globals.c/stubs.c) に HeapAlloc 呼出しラッパーを足して wasm を作る (#1171)。
# 実行は scripts/kh1171_heap_run.mjs。要 emsdk・KH_EM_CACHE。
set -e
D="$1"
LIC=$(cd "$(dirname "$0")/.." && pwd)
cd "$D"
cat > heaptest.c <<'CEOF'
#include <emscripten.h>
#include <stdint.h>
typedef uint64_t u64;
extern u64 rax, rcx, rdx, r8, r9;
u64 HeapAlloc(void);
EMSCRIPTEN_KEEPALIVE u64 test_heap(u64 n) { r8 = n; return HeapAlloc(); }
CEOF
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
export EM_CACHE="$KH_EM_CACHE"
emcc -w -O1 -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=96MB -sENVIRONMENT=node -sMODULARIZE=1 \
  -sEXPORT_NAME=KhLic -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry \
  -sEXPORTED_FUNCTIONS=_test_heap,_malloc,_free,_kh_stack_ptr \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAP32,HEAP64 -Wl,--no-gc-sections -I$LIC/lift \
  final.ll simd.c globals.c stubs.c heaptest.c -o heapexec.mjs
