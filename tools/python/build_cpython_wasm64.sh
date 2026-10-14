#!/usr/bin/env bash
# PY-80 (#2633): CPython 3.12.1 を wasm64-emscripten (Memory64) でビルドする。wasm32 の build_cpython_wasm.sh と同じ
# ソース・同じ configure 引数で、--host だけ wasm64 にする (configure.ac が wasm64-*-emscripten で -sMEMORY64=1 を
# CFLAGS / LDFLAGS に足す)。native build-python (work/build-native) を流用し、出力は work/build-wasm64 (wasm32 とは別)。
# MEMORY64_LEVEL=2: -sMEMORY64=2 (binaryen の memory64/table64 lowering。node 22 の V8 は table64 を検証できないため)
#   host は wasm32 のまま CFLAGS / LDFLAGS に -sMEMORY64=2 を渡す。出力は work/build-wasm64l。
# 使い方: bash tools/python/build_cpython_wasm64.sh   (前提: build_cpython_wasm.sh 済み)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/work"
PYVER=3.12.1
SRC="$WORK/Python-$PYVER"
BP="$WORK/build-native/python"
[ -x "$BP" ] || { echo "build-native/python が無い。先に build_cpython_wasm.sh を実行" >&2; exit 2; }
if [ "${MEMORY64_LEVEL:-1}" = 2 ]; then
  BDIR=build-wasm64l; HOST=wasm32-unknown-emscripten; FLAGS=(CFLAGS=-sMEMORY64=2 LDFLAGS=-sMEMORY64=2)
else
  BDIR=build-wasm64; HOST=wasm64-unknown-emscripten; FLAGS=()
fi

# shellcheck disable=SC1091
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
mkdir -p "$WORK/$BDIR"
cd "$WORK/$BDIR"
if [ ! -f Makefile ]; then
  env py_cv_module__sqlite3=n/a py_cv_module_xxlimited=n/a py_cv_module_xxlimited_35=n/a \
      py_cv_module__codecs_cn=n/a py_cv_module__codecs_hk=n/a py_cv_module__codecs_iso2022=n/a \
      py_cv_module__codecs_jp=n/a py_cv_module__codecs_kr=n/a py_cv_module__codecs_tw=n/a \
      py_cv_module__multibytecodec=n/a \
    CONFIG_SITE="$SRC/Tools/wasm/config.site-wasm32-emscripten" \
    emconfigure "$SRC/configure" -C \
      --host="$HOST" \
      --build="$("$SRC/config.guess")" \
      --with-emscripten-target=browser \
      --disable-ipv6 \
      OPT="-DNDEBUG -fwrapv -O3" \
      "${FLAGS[@]}" \
      --with-build-python="$BP" >configure.log 2>&1
fi
emmake make -j"$(nproc)" python.js >make.log 2>&1
grep -c -- "-sMEMORY64=" make.log || true
ls -la libpython3.12.a python.js python.wasm python.data
