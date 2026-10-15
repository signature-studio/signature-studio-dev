#!/usr/bin/env bash
# libpython3.12.a + flpy.c(+_flhost) を ES module 形式 (flpy.js / flpy.wasm / flpy.data) にリンクする。
# 前提: bash build_cpython_wasm.sh 済み。出力: tools/python/dist/ (gitignore)
# 入力 (環境変数。既定は従来どおり。詳細は analysis/flapi_table.py 冒頭):
#   EMSDK_DIR (既定 /opt/emsdk) / FL_WIN64_DIR・FL_WIN_PE (win PE) / FL_STUBS_DIR (既定 work/fl-stubs) /
#   FL_ENGINE_DYLIB (mac dylib。無ければ flapi_table.json の既存値を引き継ぐ) / FLAPI_OUT_DIR (既定 analysis/flapi)
#   FLPY_TABLE_ONLY=1: flapi_table.json / flapi_ids.json / FLAPI.md の再生成だけして終了 (emsdk・CPython wasm 不要)
#   FLPY_SKIP_TABLE=1: 上の再生成をせず、FLAPI_OUT_DIR の追跡済み flapi_table.json をそのまま使う (win PE / fl-stubs が無い環境で link だけ試す用。表は更新されない)
#   FLPY_C=<flpy.c の path (既定 src/flpy.c)> FLPY_OUT=<出力 dir (既定 dist)>  (tests/subinterp_negcontrol_old.sh が修正前 flpy.c を別 dir にビルドするのに使う)
# 入力が欠けていれば flapi_table.py が理由を出して exit 2 し、この script も非 0 で止まる (成果物は書き換えない)。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/../shared/env.sh"   # FL_WIN64_DIR / FL_MAC_DIR (docs/REFERENCES.md §4)
OUTF="${FLAPI_OUT_DIR:-$HERE/analysis/flapi}"
EMSDK_DIR="${EMSDK_DIR:-/opt/emsdk}"
[ "${FLPY_TABLE_ONLY:-0}" = 1 ] || [ -f "$EMSDK_DIR/emsdk_env.sh" ] || { echo "build_flpy.sh: ERROR: emsdk が無い: $EMSDK_DIR/emsdk_env.sh (EMSDK_DIR を指定。Actions は oc_artifacts: toolchain-emsdk)" >&2; exit 2; }
[ "${FLPY_SKIP_TABLE:-0}" = 1 ] || python3 "$HERE/analysis/flapi_table.py" >/dev/null   # flapi_table.json / flapi_ids.json を再生成 (入力欠落なら exit 2 で停止)
[ "${FLPY_TABLE_ONLY:-0}" = 1 ] && { echo "FLPY_TABLE_ONLY=1: table 再生成のみで終了 ($OUTF)"; exit 0; }
WORK="$HERE/work"; SRC="$WORK/Python-3.12.1"; B="$WORK/build-wasm"; D="${FLPY_OUT:-$HERE/dist}"; ST="$WORK/staging"; C="${FLPY_C:-$HERE/src/flpy.c}"
# shellcheck disable=SC1091
source "$EMSDK_DIR/emsdk_env.sh" >/dev/null 2>&1

rm -rf "$ST"; mkdir -p "$ST/fl/Lib" "$ST/usr/local/lib/python3.12/lib-dynload" "$D"
cp "$HERE/src/fl_rt.py" "$HERE/src/fl_api.py" "$HERE/src/flpianoroll.py" "$HERE/src/enveditor.py" "$HERE/src/flcpt.py" "$OUTF/flapi_table.json" "$ST/fl/Lib/"
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
