#!/usr/bin/env bash
# side_build.sh: 相対化 lift の産物 (lift_build.sh を OTT_RELOC=1 で作ったディレクトリ) を SIDE_MODULE にビルドし、
#   それを dlopen する薄い MAIN_MODULE=2 host (side_host.c) を作る。PERF-P8 real の PIC 税測定 (#1201) 用。
#   env: SIDE_LIFT (既定 tools/ott/work/lift_reloc)  SIDE_OUT (既定 tools/ott/work/side_reloc)  SIDE_VIS (hidden | default, 既定 hidden)
#   出力: $SIDE_OUT/side.wasm (dlopen される side module) と $SIDE_OUT/host.cjs (+ host.wasm)。
#   compile の最適化・FP フラグは lift_build.sh の std profile (liftlib/stdbuild.py flags std) と同じ。compile の差分は
#   -fPIC -fvisibility=... -sSIDE_MODULE=2 と side_compat.h (診断用 stderr のみ side_stderr() 経由にする。SIDE_MODULE は main の stderr を GOT で受けられないため)。
#   link は lift_build.sh にある -sGLOBAL_BASE・-Wl,--initial-memory/--max-memory・-sMODULARIZE・-sEXIT_RUNTIME・-sALLOW_MEMORY_GROWTH・-sSTACK_SIZE・-sENVIRONMENT を持たない。
#   host (side_host.c) は -O2 で別に作り、side の関数は host_run を介して呼ぶ。呼出し経路の差は REPORT_P8.md §9 (b)。
set -euo pipefail
OTT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
source "$OTT/../shared/env.sh"
LIFT="${SIDE_LIFT:-$OTT/work/lift_reloc}"
OUT="${SIDE_OUT:-$OTT/work/side_reloc}"
VIS="${SIDE_VIS:-hidden}"
mkdir -p "$OUT"
source "${EMSDK_DIR:-/opt/emsdk}/emsdk_env.sh" >/dev/null 2>&1
FLAGS="$(python3 "$OTT/../liftlib/liftlib/stdbuild.py" flags std)"
if [ "${SIDE_ONLY_HOST:-0}" != "1" ]; then
# shellcheck disable=SC2086
emcc $FLAGS -I"$OTT/rt" -include "$OTT/lift/side_compat.h" -fPIC -fvisibility="$VIS" \
  "$LIFT/ott_lifted.c" "$LIFT/ott_data.c" "$OTT/rt/ott_cpu.c" "$OTT/rt/ott_glue.c" "$OTT/rt/ott_ovr.c" \
  -w -sSIDE_MODULE=2 -sEXPORTED_FUNCTIONS=_ott_run,_ott_xmm0,_ott_set_stackarg,_ott_data_install,_ott_rget,_ott_set_gbase \
  -o "$OUT/side.wasm"
fi
emcc -O2 "$OTT/lift/side_host.c" -w -sMAIN_MODULE=2 -sFORCE_FILESYSTEM=1 -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createHost \
  -sINITIAL_MEMORY=$((0x36000000)) -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sINVOKE_RUN=0 -sEXIT_RUNTIME=0 \
  -sEXPORT_ALL=1 -sEXPORTED_FUNCTIONS=_host_load,_host_set_gbase,_host_data_install,_host_run,_host_error,_side_stderr,___multi3,_fma,_fiprintf,_abort,_malloc,_calloc \
  -sEXPORTED_RUNTIME_METHODS=FS,HEAPU32,HEAPF32,UTF8ToString -o "$OUT/host.cjs"
echo "[side_build] OK: $OUT/side.wasm ($(stat -c %s "$OUT/side.wasm") B) + $OUT/host.cjs"
