#!/usr/bin/env bash
# 対照実験: trace_soft_fix ビルドの GetLocaleInfoW / EnumCalendarInfoW を `--wrap` で旧 M11 stub と同じ 0 返却に差し替えて起動する。
# 結果が「同じ _UStrAsg OOB (unit #18)」なら unit #18 の停止は shimx のロケール実装に起因しない。 (前提: bash e2e.sh 済み)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; W="$HERE/../work/shimx_link"; T="$W/exp"; mkdir -p "$T"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"; source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
cat > "$T/w.c" <<'C'
int __wrap_GetLocaleInfoW(unsigned l, unsigned t, void* b, int n) { return 0; }
int __wrap_EnumCalendarInfoW(void* p, unsigned l, unsigned c, unsigned t) { return 0; }
C
emcc -c "$T/w.c" -o "$T/w.o" -w
EXPORTS=$(grep -o 'EXPORTS=[^ ]*' "$HERE/build.sh" | head -1 | cut -d= -f2)
O="$W/obj"
emcc $O/sx_*.o $O/m11_rt.o $O/m11_ov.o $O/m11_simd.o $O/m11_fnstubs.o $O/m11_data.o $O/m11_sxfix.o $O/gui_soft_fix.o $O/gui_compat.o \
  $O/boot_trace_fix.o $O/trace_wrap_fix.o $O/trace_rt.o "$T/w.o" -o "$T/exp_locale0.cjs.tmp" -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB \
  -sGLOBAL_BASE=$((0x10000000)) -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=m11create -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 --no-entry \
  -Wl,--export-all -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPU32,ENV -sEXPORTED_FUNCTIONS=$EXPORTS \
  -Wl,--initial-memory=$((0x13000000)) -Wl,--max-memory=$((0x72000000)) -Wl,--wrap=GetLocaleInfoW -Wl,--wrap=EnumCalendarInfoW 2> "$T/link.log" || { grep -m3 "error" "$T/link.log" | cut -c1-200; exit 1; }
mv "$T/exp_locale0.cjs.tmp" "$T/exp_locale0.cjs"
node "$HERE/run_trace.mjs" "$T/exp_locale0.cjs" --out "$T" | cut -c1-400
