#!/usr/bin/env bash
# PY-2 (#83): CPython (libpython3.12.a) + flpy.c + flapi provider (fl_api_call) を 1 つの wasm にリンクする。
#   _flhost.call は同一 wasm 内の C 呼出し (JS import・JSON・SAB・Worker いずれも経由しない)。
# 前提: bash build_cpython_wasm.sh 済み (work/build-wasm)。出力: dist/flpy_static.{js,wasm,data} (gitignore)
# PY-98 (#2858): FLPY_MEMORY64=1 で wasm64 版 (dist/flpy_static64.*) を作る。CPY_BUILD=<libpython の build dir> (既定 work/build-wasm64)。
#   前提: CPY_MEMORY64=1 bash build_cpython_wasm.sh 済み。stdlib zip は wasm32 版 (work/build-wasm) を流用する。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FLPY_MEMORY64="${FLPY_MEMORY64:-0}"
if [ "$FLPY_MEMORY64" = 1 ]; then
  DEF_OUT=flpy_static64; CB="${CPY_BUILD:-$HERE/work/build-wasm64}"; MEM="-sMEMORY64=1"
else
  DEF_OUT=flpy_static; CB="${CPY_BUILD:-$HERE/work/build-wasm}"; MEM=""
fi
OUT="${STATIC_OUT:-$DEF_OUT}"        # ネガコン用: STATIC_OUT=flpy_static_neg ENGINE_SRC=<改変した fl_engine.c>
WORK="$HERE/work"; SRC="$WORK/Python-3.12.1"; B="$WORK/build-wasm"; D="$HERE/dist"; ST="$WORK/staging_$OUT"
P="$HERE/provider"
ENGINE_SRC="${ENGINE_SRC:-$P/fl_engine.c}"
# shellcheck disable=SC1090
source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1

python3 "$P/gen_provider.py" --check-handlers "$ENGINE_SRC"
rm -rf "$ST"; mkdir -p "$ST/fl/Lib" "$ST/usr/local/lib/python3.12/lib-dynload" "$D"
cp "$HERE/src/fl_rt.py" "$HERE/src/fl_api.py" "$HERE/analysis/flapi/flapi_table.json" "$ST/fl/Lib/"
cp "$B/usr/local/lib/python312.zip" "$ST/usr/local/lib/"
touch "$ST/usr/local/lib/python3.12/lib-dynload/.empty"

emcc -O2 -g0 $MEM -DFLPY_STATIC -I"$SRC/Include" -I"$CB" -I"$P" -c "$HERE/src/flpy.c" -o "$WORK/$OUT.o"
emcc -O2 -g0 $MEM -I"$HERE/analysis/pybind" -c "$HERE/src/pybind_resolve.c" -o "$WORK/pybind_resolve.o"
emcc -O2 -g0 $MEM -Wall -Wextra -Wno-unused-parameter -Wno-unused-variable -Wno-unused-but-set-variable \
  "$WORK/$OUT.o" "$WORK/pybind_resolve.o" "$P/fl_dispatch.c" "$ENGINE_SRC" "$P/gen/fl_table.c" "$CB/libpython3.12.a" \
  "$CB/Modules/_decimal/libmpdec/libmpdec.a" "$CB/Modules/_hacl/libHacl_Hash_SHA2.a" "$CB/Modules/expat/libexpat.a" \
  -sUSE_ZLIB -sUSE_BZIP2 -ldl -lm \
  --no-entry -sALLOW_MEMORY_GROWTH -sINITIAL_MEMORY=33554432 -sSTACK_SIZE=5242880 \
  -sFORCE_FILESYSTEM -sMODULARIZE -sEXPORT_ES6 -sEXPORT_NAME=createFlPythonStatic -sENVIRONMENT=web,worker,node \
  -sEXPORTED_FUNCTIONS=_flpy_init,_flpy_run,_flpy_call_json,_flpy_last_error,_flpy_free,_flpy_finalize,_flpy_trace_reset,_flpy_host_calls,_flpy_trace_len,_flpy_trace_fn,_flpy_trace_argc,_flpy_resolve,_flpy_resolve_count,_flpy_bench_c,_fl_engine_reset,_fl_engine_highlight_cb,_fl_engine_channel_count,_fl_api_call,_flpy_subinterp_run,_malloc,_free \
  -sEXPORTED_RUNTIME_METHODS=FS,UTF8ToString,stringToUTF8,lengthBytesUTF8,HEAPU8,wasmTable \
  --preload-file "$ST@/" \
  -o "$D/$OUT.js"
ls -la "$D"/"$OUT".*
