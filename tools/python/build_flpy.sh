#!/usr/bin/env bash
# libpython3.12.a + flpy.c(+_flhost) を ES module 形式 (flpy.js / flpy.wasm / flpy.data) にリンクする。
# 前提: bash build_cpython_wasm.sh 済み。出力: tools/python/dist/ (gitignore)
# 環境変数: FLPY_C=<flpy.c の path (既定 src/flpy.c)> FLPY_OUT=<出力 dir (既定 dist)> FLPY_SKIP_TABLE=1  (tests/subinterp_negcontrol_old.sh が修正前 flpy.c を別 dir にビルドするのに使う)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/work"; SRC="$WORK/Python-3.12.1"; B="$WORK/build-wasm"; D="${FLPY_OUT:-$HERE/dist}"; ST="$WORK/staging"; C="${FLPY_C:-$HERE/src/flpy.c}"
# shellcheck disable=SC1091
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1

# FLPY_SKIP_TABLE=1: 追跡済みの flapi_table.json をそのまま使う (win PE / fl-stubs が無い環境では再生成が表を劣化させる)
[ "${FLPY_SKIP_TABLE:-0}" = 1 ] || python3 "$HERE/analysis/flapi_table.py" >/dev/null   # flapi_table.json / flapi_ids.json を再生成
rm -rf "$ST"; mkdir -p "$ST/fl/Lib" "$ST/usr/local/lib/python3.12/lib-dynload" "$D"
cp "$HERE/src/fl_rt.py" "$HERE/src/fl_api.py" "$HERE/analysis/flapi/flapi_table.json" "$ST/fl/Lib/"
cp "$B/usr/local/lib/python312.zip" "$ST/usr/local/lib/"
touch "$ST/usr/local/lib/python3.12/lib-dynload/.empty"

emcc -O2 -g0 -I"$SRC/Include" -I"$B" -c "$C" -o "$WORK/flpy.o"
emcc -O2 -g0 "$WORK/flpy.o" "$B/libpython3.12.a" \
  "$B/Modules/_decimal/libmpdec/libmpdec.a" "$B/Modules/_hacl/libHacl_Hash_SHA2.a" "$B/Modules/expat/libexpat.a" \
  -sUSE_ZLIB -sUSE_BZIP2 -ldl -lm \
  --no-entry -sALLOW_MEMORY_GROWTH -sINITIAL_MEMORY=33554432 -sSTACK_SIZE=5242880 \
  -sFORCE_FILESYSTEM -sMODULARIZE -sEXPORT_ES6 -sEXPORT_NAME=createFlPython -sENVIRONMENT=web,worker,node \
  -sEXPORTED_FUNCTIONS=_flpy_init,_flpy_run,_flpy_call_json,_flpy_subinterp_run,_flpy_last_error,_flpy_free,_flpy_finalize,_malloc,_free \
  -sEXPORTED_RUNTIME_METHODS=FS,UTF8ToString,stringToUTF8,lengthBytesUTF8,HEAPU8,ccall,cwrap \
  --js-library "$HERE/src/flhost_lib.js" --preload-file "$ST@/" \
  -o "$D/flpy.js"
ls -la "$D"
