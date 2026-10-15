#!/usr/bin/env bash
# cpi_pool_probe.sh: cpi_reach.sh の停止点 f_4079e0 (割当て管理) の入力を実測する (#5252)。
#   usage: FL_WIN64_DIR=<fl-win64>/extracted EMSDK=<emsdk> PATH=<emsdk>/upstream/emscripten:$PATH \
#          bash tools/hostbridge/wrapper_lift/cpi_pool_probe.sh block19091_PE.bin <work>
#   前提: <work>/probe/ott_lifted_probe.c と <work>/probe/cpi_probe.o 等は cpi_reach.sh を先に 1 回流して作る。
#   出力: <work>/probe/dbg2.cjs と stderr の [dbg] 行 (進入した関数と rcx/rdx/rbx/rax)。repo には書かない。
#   判定: [dbg] enter4079e0 の後に enter41bcf0・enter409070・enter4091c0 が出なければ、割当てプールの初期化は走っていない。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
BLOCK="$1"
W="$2"
RT="$REPO/tools/ott/rt"
P="$W/probe"
[ -f "$P/ott_lifted_probe.c" ] || { echo "[pool] $P/ott_lifted_probe.c が無い。先に cpi_reach.sh を流す" >&2; exit 2; }
BASE="$(python3 "$HERE/cpi_image.py" "$FL_WIN64_DIR/$BLOCK" "$W/image.bin")"

cat > "$P/cpi_dbg.c" <<'EOF'
#include "ott_cpu.h"
#include <stdio.h>
void cpi_dbg(const char* tag, unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d) {
    fprintf(stderr, "[dbg] %s rcx=%#llx rdx=%#llx rbx=%#llx rax=%#llx\n", tag, a, b, c, d);
}
EOF

sed -e '1i void cpi_dbg(const char*, unsigned long long, unsigned long long, unsigned long long, unsigned long long);' \
  -e '/^void f_41bcf0(void) {/a cpi_dbg("enter41bcf0", R[1], R[2], R[3], R[0]);' \
  -e '/^void f_409070(void) {/a cpi_dbg("enter409070", R[1], R[2], R[3], R[0]);' \
  -e '/^void f_4091c0(void) {/a cpi_dbg("enter4091c0", R[1], R[2], R[3], R[0]);' \
  -e '/^void f_408900(void) {/a cpi_dbg("enter408900", R[1], R[2], R[3], R[0]);' \
  -e '/^void f_4079e0(void) {/a cpi_dbg("enter4079e0", R[1], R[2], R[3], R[0]);' \
  "$P/ott_lifted_probe.c" > "$P/dbg2_lifted.c"

emcc -c -w -I "$RT" "$P/dbg2_lifted.c" -o "$P/dbg2_ott.o"
emcc -c -w -I "$RT" "$P/cpi_dbg.c" -o "$P/cpi_dbg.o"
emcc -I "$RT" "$P/dbg2_ott.o" "$P/cpi_probe.o" "$P/cpi_host.o" "$P/cpi_dbg.o" \
  "$RT/ott_cpu.c" "$RT/ott_glue.c" "$RT/ott_ovr.c" \
  -w -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sEXPORTED_FUNCTIONS=_ott_run,_ott_xmm0,_ott_rget,_malloc,_cpi_ring_addr,_cpi_count,_cpi_host_setup \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
  -o "$P/dbg2.cjs"

node "$HERE/cpi_pool_drive.mjs" "$P/dbg2.cjs" "$W/image.bin" "$BASE" 0x86ab10 0xa00000
