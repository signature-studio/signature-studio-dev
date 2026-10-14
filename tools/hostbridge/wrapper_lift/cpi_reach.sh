#!/usr/bin/env bash
# cpi_reach.sh: x64c で生成した Fruity Wrapper の C を wasm (node 用 MODULARIZE) にし、CreatePlugInstance (VA 0x86ab10) への入場を確認する (#829 受入 2)。
#   usage: FL_WIN64_DIR=<fl-win64>/extracted EM_CONFIG=... PATH=<emsdk>/upstream/emscripten:$PATH \
#          bash tools/hostbridge/wrapper_lift/cpi_reach.sh block19091_PE.bin <work>
#   <work>/x64c/ott_lifted.c は x64c_wrapper.py の出力 (先に生成しておく)。出力は <work>/probe/ と <work>/cpi.cjs。
#   判定: node cpi_reach.mjs の JSON で entered=true なら入場ログ ([cpi] enter 0x86ab10) を確認。false なら最初に失敗した地点 (err) を記録する。
# 注意: 複製 C を使う (<work>/probe/ 配下のみ。repo には書かない)。f_86ab10 の先頭に cpi_enter を、各命令コメント行の後に cpi_at(VA) を挿入し、
#       直近 256 命令を wasm メモリの ring に残す (trap 後も node から読める)。a0 (host) は cpi_reach.mjs の引数で与える。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
BLOCK="$1"
W="$2"
mkdir -p "$W/probe"
BASE="$(python3 "$HERE/cpi_image.py" "$FL_WIN64_DIR/$BLOCK" "$W/image.bin")"
echo "[cpi] image ImageBase=$BASE -> $W/image.bin"
[ "$(grep -c '^void f_86ab10(void) {$' "$W/x64c/ott_lifted.c")" = "1" ] || { echo "[cpi] f_86ab10 の定義が 1 箇所でない" >&2; exit 2; }
sed -e '1i void cpi_enter(unsigned long long); void cpi_at(unsigned long long);' \
  -e 's/^void f_86ab10(void) {$/void f_86ab10(void) { cpi_enter(0x86ab10ULL);/' \
  -e 's/^  \/\* \([0-9a-f]*\): \(.*\) \*\/$/  \/* \1: \2 *\/ cpi_at(0x\1ULL);/' \
  "$W/x64c/ott_lifted.c" > "$W/probe/ott_lifted_probe.c"
RT="$REPO/tools/ott/rt"
emcc -c -I "$RT" "$W/probe/ott_lifted_probe.c" -o "$W/probe/ott_probe.o"
emcc -c "$HERE/cpi_probe.c" -o "$W/probe/cpi_probe.o"
emcc -I "$RT" "$W/probe/ott_probe.o" "$W/probe/cpi_probe.o" \
  "$RT/ott_cpu.c" "$RT/ott_glue.c" "$RT/ott_ovr.c" \
  -w -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sEXPORTED_FUNCTIONS=_ott_run,_ott_xmm0,_ott_rget,_malloc,_cpi_ring_addr,_cpi_count \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
  -o "$W/cpi.cjs"
node "$HERE/cpi_reach.mjs" "$W/cpi.cjs" "$W/image.bin" "$BASE" 0x86ab10
