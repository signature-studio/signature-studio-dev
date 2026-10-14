#!/usr/bin/env bash
# T-SH-33 (#1748): QuickFontCache が解決する FT_* 14 本の import 表 (qfc_import.c) を経由して FreeType 2.7 を呼び、
# native / wasm32 / wasm64 の出力が一致することを確認する。build.sh が作ったライブラリ (work/build/freetype) を使う。
# usage: bash oss/freetype/qfc_import_e2e.sh [font.ttf]   (既定: fl-mac の OpenSans-Regular.ttf)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
source "$ROOT/env.sh"
SRC="$ROOT/work/src/freetype-2.7"; B="$ROOT/work/build/freetype"
for f in "$B/native/src/objs/.libs/libfreetype.a" "$B/wasm32/src/objs/.libs/libfreetype.a" "$B/wasm64/src/objs/.libs/libfreetype.a"; do
  [ -f "$f" ] || { echo "run oss/freetype/build.sh first (missing $f)" >&2; exit 2; }
done
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
FONT="${1:-$FL_MAC_DIR/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL/Shared/Artwork/Fonts/OpenSans-Regular.ttf}"
[ -f "$FONT" ] || { echo "font not found: $FONT" >&2; exit 2; }
INC="$SRC/include"; O="$B/qfc"; mkdir -p "$O"
gcc -O2 -I"$INC" -I"$HERE" "$HERE/test_qfc_import.c" "$HERE/qfc_import.c" "$B/native/src/objs/.libs/libfreetype.a" -lm -o "$O/test_native"
emcc -O2 -I"$INC" -I"$HERE" "$HERE/test_qfc_import.c" "$HERE/qfc_import.c" "$B/wasm32/src/objs/.libs/libfreetype.a" -o "$O/test_wasm32.cjs" \
  -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1
emcc -O2 -sMEMORY64=1 -I"$INC" -I"$HERE" "$HERE/test_qfc_import.c" "$HERE/qfc_import.c" "$B/wasm64/src/objs/.libs/libfreetype.a" -o "$O/test_wasm64.cjs" \
  -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1
"$O/test_native" "$FONT" > "$O/out_native.txt"
node "$O/test_wasm32.cjs" "$FONT" > "$O/out_wasm32.txt"
node64="${EMSDK_NODE:-node}"
"$node64" "$O/test_wasm64.cjs" "$FONT" > "$O/out_wasm64.txt" 2>"$O/out_wasm64.err"
rc=0
for v in wasm32 wasm64; do
  if diff -q "$O/out_native.txt" "$O/out_$v.txt" >/dev/null; then
    echo "[qfc-import] PASS $v: native == wasm ($(wc -l < "$O/out_$v.txt") lines, $(tail -1 "$O/out_$v.txt"))"
  else diff "$O/out_native.txt" "$O/out_$v.txt" | head -6; echo "[qfc-import] FAIL $v"; rc=1; fi
done
head -1 "$O/out_native.txt"; grep '^table' "$O/out_native.txt"
exit $rc
