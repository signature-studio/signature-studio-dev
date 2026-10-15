#!/usr/bin/env bash
# cpi_reach.sh: x64c で生成した Fruity Wrapper の C を wasm (node 用 MODULARIZE) にし、CreatePlugInstance への入場と完走を確認する (#829 受入 2・#2653)。
#   usage: FL_WIN64_DIR=<fl-win64>/extracted EM_CONFIG=... PATH=<emsdk>/upstream/emscripten:$PATH \
#          bash tools/hostbridge/wrapper_lift/cpi_reach.sh block19091_PE.bin <work> [entry VA 16進 (既定 0x86ab10)] [a0 16進 (既定 0x600000 = host)]
#   <work>/x64c/ott_lifted.c は x64c_wrapper.py の出力 (先に生成しておく)。出力は <work>/probe/ と <work>/cpi.cjs。
#   判定: node cpi_reach.mjs の JSON。entered=true で入場ログ ([cpi] enter <entry>) を確認。ret が null なら trap を記録する。
#   CPI_NOENTER=1 で cpi_enter 行を入れない複製を作る (強い NC: entered が false になることを見る)。
# 注意: 複製 C を使う (<work>/probe/ 配下のみ。repo には書かない)。entry 関数の先頭に cpi_enter を、各命令コメント行の後に cpi_at(VA) を挿入し、
#       直近 256 命令を wasm メモリの ring に残す (trap 後も node から読める)。
#       host を再構成する cpi_host.c (cpi_host_setup・cpi_miss・cpi_miss_imp) を link し、ott_dispatch の default 分岐 (記録して返す) と
#       ott_missing_import の先頭 (記録して返す) を sed で差し込む。lift 出力と rt (tools/ott/rt) は変更しない。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
BLOCK="$1"
W="$2"
ENTRY="${3:-0x86ab10}"
A0="${4:-0x600000}"
ENTRY_HEX="${ENTRY#0x}"
mkdir -p "$W/probe"
BASE="$(python3 "$HERE/cpi_image.py" "$FL_WIN64_DIR/$BLOCK" "$W/image.bin")"
echo "[cpi] image ImageBase=$BASE -> $W/image.bin entry=$ENTRY a0=$A0"
[ "$(grep -c "^void f_${ENTRY_HEX}(void) {\$" "$W/x64c/ott_lifted.c")" = "1" ] || { echo "[cpi] f_${ENTRY_HEX} の定義が 1 箇所でない" >&2; exit 2; }
ENTER_SED="s/^void f_${ENTRY_HEX}(void) {\$/void f_${ENTRY_HEX}(void) { cpi_enter(${ENTRY}ULL);/"
if [ "${CPI_NOENTER:-0}" = "1" ]; then ENTER_SED="s/^void f_${ENTRY_HEX}(void) {\$/void f_${ENTRY_HEX}(void) {/"; fi
sed -e '1i void cpi_enter(unsigned long long); void cpi_at(unsigned long long); int cpi_miss(unsigned long long); int cpi_miss_imp(const char*);' \
  -e "$ENTER_SED" \
  -e 's/default: ott_unlifted(t);/default: if (cpi_miss(t)) return; ott_unlifted(t);/' \
  -e 's/ott_missing_import("\([A-Za-z_0-9]*\)"); }$/if (cpi_miss_imp("\1")) return; ott_missing_import("\1"); }/' \
  -e 's/^  \/\* \([0-9a-f]*\): \(.*\) \*\/$/  \/* \1: \2 *\/ cpi_at(0x\1ULL);/' \
  "$W/x64c/ott_lifted.c" > "$W/probe/ott_lifted_probe.c"
RT="$REPO/tools/ott/rt"
emcc -c -I "$RT" "$W/probe/ott_lifted_probe.c" -o "$W/probe/ott_probe.o"
emcc -c "$HERE/cpi_probe.c" -o "$W/probe/cpi_probe.o"
emcc -c -I "$RT" "$HERE/cpi_host.c" -o "$W/probe/cpi_host.o"
emcc -I "$RT" "$W/probe/ott_probe.o" "$W/probe/cpi_probe.o" "$W/probe/cpi_host.o" \
  "$RT/ott_cpu.c" "$RT/ott_glue.c" "$RT/ott_ovr.c" \
  -w -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sEXPORTED_FUNCTIONS=_ott_run,_ott_xmm0,_ott_rget,_malloc,_cpi_ring_addr,_cpi_count,_cpi_host_setup \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
  -o "$W/cpi.cjs"
node "$HERE/cpi_reach.mjs" "$W/cpi.cjs" "$W/image.bin" "$BASE" "$ENTRY" "$A0"
