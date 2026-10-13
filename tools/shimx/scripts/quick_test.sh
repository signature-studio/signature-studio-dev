#!/usr/bin/env bash
# 開発用: MT ビルド + 実行だけ (test.sh のフル検証より速い)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; set -u
cd "$HERE"; mkdir -p build
emcc -w -Wno-error=int-conversion -O1 -pthread -sPTHREAD_POOL_SIZE=12 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 -sENVIRONMENT=node -sERROR_ON_UNDEFINED_SYMBOLS=1 -sGLOBAL_BASE=1048576 -Isrc -Ipathreg/include src/*.c test/*.c pathreg/src/pathmap.c -o build/q.js
mv build/q.js build/q.cjs
node build/q.cjs "$@"
