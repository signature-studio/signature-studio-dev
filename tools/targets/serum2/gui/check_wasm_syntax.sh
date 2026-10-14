#!/usr/bin/env bash
# SR-29 #1920: vstguibase.h に Emscripten (wasm) 分岐を入れた後、PoC seed 6 宣言の構文チェックを
# 補正 (-D__linux__=1) なしで通すことを確認する。
# 前提: work/vstgui4 (vstgui4_14_3 の clone)、work/emsdk/upstream/emscripten (toolchain-emsdk の展開)。
# usage: bash check_wasm_syntax.sh   (cwd は gui/ でなくてもよい)
set -u
here="$(cd "$(dirname "$0")" && pwd)"
work="$here/work"
export EM_IGNORE_SANITY=1
export PATH="$work/emsdk/upstream/emscripten:$PATH"

cd "$work/vstgui4" || exit 2
if ! git diff --quiet -- vstgui/lib/vstguibase.h; then
  echo "vstguibase.h は既に変更済み (patch 適用済み扱い)"
else
  git apply "$here/patches/vstguibase_emscripten.patch" || exit 2
fi

printf '%s\n' \
  '#include "vstgui/lib/controls/ctextlabel.h"' \
  '#include "vstgui/lib/cviewcontainer.h"' \
  '#include "vstgui/lib/cview.h"' \
  '#include "vstgui/lib/controls/ccontrol.h"' \
  '#include "vstgui/lib/cbitmap.h"' \
  '#include "vstgui/lib/cdrawcontext.h"' > "$work/seed6.cpp"

timeout 200 em++ -std=c++17 -fsyntax-only -I. "$work/seed6.cpp" > "$work/seed6_after.log" 2>&1
rc=$?
echo "seed6 syntax check (no -D__linux__ workaround): rc=$rc errors=$(grep -c 'error' "$work/seed6_after.log")"
exit $rc
