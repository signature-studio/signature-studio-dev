#!/usr/bin/env bash
# SR-35 #2064: canvas platform (wasm) の実装ファイルを em++ -fsyntax-only で検査する。
# 前提: work/vstgui4 (vstgui4_14_3)、work/emsdk/upstream/emscripten (toolchain-emsdk の展開)。
# usage: bash check_canvas_syntax.sh
set -u
here="$(cd "$(dirname "$0")" && pwd)"
gui="$(dirname "$here")"
work="$gui/work"
export EM_IGNORE_SANITY=1
export PATH="$work/emsdk/upstream/emscripten:$PATH"

cd "$work/vstgui4" || exit 2
if ! git diff --quiet -- vstgui/lib/vstguibase.h vstgui/lib/platform/platformfwd.h; then
  echo "vstguibase.h / platformfwd.h は既に変更済み (patch 適用済み扱い)"
else
  git apply "$gui/patches/vstguibase_emscripten.patch" || exit 2
  git apply "$gui/patches/platformfwd_emscripten.patch" || exit 2
fi

rc_all=0
for f in "$here"/canvas_bitmap.cpp "$here"/canvas_graphicspath.cpp \
         "$here"/canvas_frame.cpp \
         "$here"/canvas_font.cpp "$here"/canvas_graphicsdevice.cpp \
         "$here"/canvas_platformfactory.cpp "$here"/canvas_string.cpp; do
  log="$work/$(basename "$f").log"
  timeout 200 em++ -std=c++17 -fsyntax-only -I. -I"$here" "$f" > "$log" 2>&1
  rc=$?
  echo "$(basename "$f"): rc=$rc errors=$(grep -c 'error' "$log")"
  [ $rc -ne 0 ] && rc_all=1
done
exit $rc_all
