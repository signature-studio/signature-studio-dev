#!/usr/bin/env bash
# #1630 SHX-T27 対照実験: build.sh --trace --soft 済みの .o 一式を、API を `--wrap` で差し替えて再リンクして起動する。
#   bash experiments/t27_relink.sh locale0    GetLocaleInfoW / EnumCalendarInfoW を旧 M11 stub と同じ 0 返却にする
#   bash experiments/t27_relink.sh none       差し替え無し (build.sh --trace --soft と同じ構成の再リンク。対照)
# 前提: bash tools/m11/shimx_link/build.sh --trace --soft 済み。成果物は work/shimx_link/exp_t27/ (gitignore 済)。
set -euo pipefail
MODE="${1:?mode (locale0|none)}"
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; W="$HERE/../work/shimx_link"; T="$W/exp_t27"; O="$W/obj"; mkdir -p "$T"
EMENV="$(grep -o '[^ ]*emsdk_env.sh' "$HERE/build.sh" | head -1)"   # build.sh と同じ emsdk (REFERENCES [EMSDK]) を使う
set +u; source "$EMENV" > /dev/null 2>&1; set -u
export PATH="$(dirname "$EMENV")/upstream/bin:$PATH"
WRAPS="-Wl,--wrap=m11_icall"; EXTRA=""
case "$MODE" in
  locale0)
    cat > "$T/w_locale0.c" <<'C'
int __wrap_GetLocaleInfoW(unsigned l, unsigned t, void* b, int n) { return 0; }
int __wrap_EnumCalendarInfoW(void* p, unsigned l, unsigned c, unsigned t) { return 0; }
C
    emcc -c "$T/w_locale0.c" -o "$T/w_locale0.o" -w
    EXTRA="$T/w_locale0.o"; WRAPS="$WRAPS -Wl,--wrap=GetLocaleInfoW -Wl,--wrap=EnumCalendarInfoW" ;;
  none) ;;
  *) echo "unknown mode: $MODE" >&2; exit 2 ;;
esac
EXPORTS=$(grep -o 'EXPORTS=[^ ]*' "$HERE/build.sh" | head -1 | cut -d= -f2)
EXPORTS="${EXPORTS//\$\{WSEXP\}/}"
emcc "$O"/sx_*.o "$O/m11_rt.o" "$O/m11_ov.o" "$O/m11_simd.o" "$O/m11_fnstubs.o" "$O/m11_data.o" "$O/m11_sxfix.o" \
  "$O/gui_soft.o" "$O/gui_compat.o" "$O/boot_trace.o" "$O/trace_wrap.o" "$O/trace_rt.o" $EXTRA -o "$T/exp_$MODE.cjs.tmp" \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=$((0x10000000)) \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=m11create -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 --no-entry \
  -Wl,--export-all -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPF32,HEAP32,HEAPF64,HEAPU32,HEAP64,wasmTable,addFunction,ENV,ccall,FS \
  -sEXPORTED_FUNCTIONS="$EXPORTS" \
  -Wl,--initial-memory=$((0x13000000)) -Wl,--max-memory=$((0x72000000)) $WRAPS 2> "$T/link_$MODE.log" \
  || { grep -m3 "error" "$T/link_$MODE.log" | cut -c1-200; exit 1; }
mv "$T/exp_$MODE.cjs.tmp" "$T/exp_$MODE.cjs"
SHIMX_TRACE_FILE=/ftrace.jsonl node "$HERE/run_trace.mjs" "$T/exp_$MODE.cjs" --out "$T" | cut -c1-700
echo "ftrace lines: $(wc -l < "$T/exp_$MODE.ftrace.jsonl")"
