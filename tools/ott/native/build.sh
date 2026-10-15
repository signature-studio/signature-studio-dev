#!/usr/bin/env bash
# native 参照ローダ (libottnative.so) をビルド: gcc -shared (x86_64 Linux)
set -euo pipefail
D="$(cd -- "$(dirname -- "$0")" && pwd)"
mkdir -p "$D/../work"
gcc -O1 -g -fPIC -fno-omit-frame-pointer -shared -o "$D/../work/libottnative.so" "$D/ott_native.c" "$D/ms_call.S"
echo "[native/build] OK work/libottnative.so"
