#!/usr/bin/env bash
# CPython 3.12.1 (= FL Studio 26.1.7 同梱版) を emscripten (wasm32) でビルドする。
#   1) native build-python (3.12.1)   -> work/build-native   (cross-build 用 + dis 用)
#   2) wasm32-emscripten (browser 系) -> work/build-wasm     (libpython3.12.a / python.js(stock) / usr/local stdlib zip)
# 使い方: bash tools/python/build_cpython_wasm.sh   (再実行可: incremental)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/work"
PYVER=3.12.1
SRC="$WORK/Python-$PYVER"
mkdir -p "$WORK"

if [ ! -d "$SRC" ]; then
  [ -f "$WORK/Python-$PYVER.tgz" ] || curl -sSL -o "$WORK/Python-$PYVER.tgz" "https://www.python.org/ftp/python/$PYVER/Python-$PYVER.tgz"
  tar -C "$WORK" -xzf "$WORK/Python-$PYVER.tgz"
fi

# --- 1) native build python (emsdk を PATH から外す) ---
if [ ! -x "$WORK/build-native/python" ]; then
  mkdir -p "$WORK/build-native"
  (
    cd "$WORK/build-native"
    PATH="$(echo "$PATH" | tr ':' '\n' | grep -v emsdk | paste -sd:)"
    "$SRC/configure" -C --prefix="$PWD/install" >configure.log 2>&1
    make -j"$(nproc)" >make.log 2>&1
    make install >install.log 2>&1
  )
fi

# --- 2) wasm32-emscripten ---
# shellcheck disable=SC1091
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
BP="$WORK/build-native/python"
mkdir -p "$WORK/build-wasm"
cd "$WORK/build-wasm"
if [ ! -f Makefile ]; then
  # 不要/ビルド不能モジュールを configure 段階で無効化 (sqlite3: port 依存を避ける, xxlimited: 動的リンク用 -fPIC 要求, CJK codec: 約 1MB)
  env py_cv_module__sqlite3=n/a py_cv_module_xxlimited=n/a py_cv_module_xxlimited_35=n/a \
      py_cv_module__codecs_cn=n/a py_cv_module__codecs_hk=n/a py_cv_module__codecs_iso2022=n/a \
      py_cv_module__codecs_jp=n/a py_cv_module__codecs_kr=n/a py_cv_module__codecs_tw=n/a \
      py_cv_module__multibytecodec=n/a \
    CONFIG_SITE="$SRC/Tools/wasm/config.site-wasm32-emscripten" \
    emconfigure "$SRC/configure" -C \
      --host=wasm32-unknown-emscripten \
      --build="$("$SRC/config.guess")" \
      --with-emscripten-target=browser \
      --disable-ipv6 \
      OPT="-DNDEBUG -fwrapv -O3" \
      --with-build-python="$BP" >configure.log 2>&1
fi
# stock python.js (node/browser 用 CLI) まで通す。共有 ext module (xxlimited 等) は静的化されるので不要。
emmake make -j"$(nproc)" python.js >make.log 2>&1
ls -la libpython3.12.a python.js python.wasm python.data

# LGL-3 (#86): 再ビルド記録 (upstream 版・ソース sha256・configure 引数)。build_flpy.sh は CPython ソースにパッチを当てない
node "$HERE/../legal/notices/record.mjs" --id "cpython-$PYVER" --name CPython --version "$PYVER" --license-spdx PSF-2.0 \
  --url "https://www.python.org/ftp/python/$PYVER/Python-$PYVER.tgz" --archive "$WORK/Python-$PYVER.tgz" \
  --src-dir "$SRC" --license-file LICENSE \
  --script "$HERE/build_cpython_wasm.sh" --toolchain emcc --target wasm32 \
  --step "configure-native=./configure -C (emsdk を PATH から外した native build python 用)" \
  --step "configure-wasm=env py_cv_module__sqlite3=n/a py_cv_module_xxlimited=n/a py_cv_module_xxlimited_35=n/a py_cv_module__codecs_cn=n/a py_cv_module__codecs_hk=n/a py_cv_module__codecs_iso2022=n/a py_cv_module__codecs_jp=n/a py_cv_module__codecs_kr=n/a py_cv_module__codecs_tw=n/a py_cv_module__multibytecodec=n/a CONFIG_SITE=Tools/wasm/config.site-wasm32-emscripten emconfigure ./configure -C --host=wasm32-unknown-emscripten --build=<config.guess> --with-emscripten-target=browser --disable-ipv6 OPT=\"-DNDEBUG -fwrapv -O3\" --with-build-python=<native python>" \
  --step "make=emmake make python.js"
