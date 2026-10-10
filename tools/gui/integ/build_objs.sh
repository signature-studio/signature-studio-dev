#!/usr/bin/env bash
# build_objs.sh — 実 FLEngine 結合 (CAB-173) 用に shim を .o 群として出力する (m11_build.sh の work/obj/*.o にそのまま加えられる形)。
#   usage: build_objs.sh <outdir> [--reach] [--ir path.ll] [--no-pthread]
#   出力: gui_core.o gui_gdi.o gui_stubs.o (gui_impl_<Name> へ改名 + GUI_NO_K32) / gui_platform.o gui_reach.o gui_reach_tab.o /
#         gui_adapt_w32.o (IR 署名 adapter; --reach なら到達ログ付き) / exports.txt (定義シンボル; m11 の defined_c.txt に追記する)
#   既定は -pthread (shim は futex 待機を使う; 結合先の全 TU も -pthread で揃えること — INTEGRATION.md §4)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; GUI="$HERE/.."; BUILD="$GUI/build"
OUT="$1"; shift; REACH=0; IR=(); PT=(-pthread)
while [ $# -gt 0 ]; do case "$1" in --reach) REACH=1;; --ir) IR=(--ir "$2"); shift;; --no-pthread) PT=();; esac; shift; done
mkdir -p "$OUT"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
python3 "$GUI/gen_api.py" >/dev/null
python3 "$HERE/gen_adapt.py" ${IR[@]+"${IR[@]}"} --no-md | tail -1
CF=(-O1 -fwrapv -w -fno-strict-aliasing ${PT[@]+"${PT[@]}"} -I "$GUI/include" -I "$GUI/src" -I "$BUILD")
RF=(); [ $REACH = 1 ] && RF=(-DGUI_REACH_LOG)
for f in "$GUI"/src/gui_core.c "$GUI"/src/gui_gdi.c "$BUILD"/gui_stubs.c; do
  emcc -c "${CF[@]}" -DGUI_NO_K32 -include "$BUILD/gui_rename.h" "$f" -o "$OUT/$(basename "$f" .c).o"; done
for f in "$GUI"/src/gui_platform.c "$GUI"/src/gui_reach.c "$BUILD"/gui_reach_tab.c; do emcc -c "${CF[@]}" "$f" -o "$OUT/$(basename "$f" .c).o"; done
emcc -c "${CF[@]}" ${RF[@]+"${RF[@]}"} "$BUILD/gui_adapt_w32.c" -o "$OUT/gui_adapt_w32.o"
llvm-nm --defined-only "$OUT"/*.o | awk '$2 ~ /^[TtWwDdBbRr]$/ {print $3}' | sort -u > "$OUT/exports.txt"
echo "[build_objs] $(ls "$OUT"/*.o | wc -l) objects -> $OUT (defined symbols: $(wc -l < "$OUT/exports.txt"); reach=$REACH pthread=$([ ${#PT[@]} -gt 0 ] && echo 1 || echo 0))"
