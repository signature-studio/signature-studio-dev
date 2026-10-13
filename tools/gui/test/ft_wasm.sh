#!/usr/bin/env bash
# ft_wasm.sh — GUI-9 (#186): text engine (gui_ft.c) を native と wasm32 で走らせ、metrics/advance/glyph coverage のダンプが一致することを検査。
# wasm 側の FreeType は shim (pthread/atomics) と link できるよう tools/shared の patch 済みツリーから -pthread で作り直す (build.sh が作る work/build/freetype/wasm32/src を複製)。
# ネガティブコントロール: ダンプ 1 行を壊すと cmp が失敗すること / 素の (FORCE_INT64 + patch 無し) FT では不一致になること は oss/freetype/build.sh 側で実測済み (REPORT §11)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; B="$ROOT/build"; mkdir -p "$B"
FTW="$ROOT/../shared/work"; SRC="$FTW/build/freetype/wasm32/src"; FONTDIR="${FONTDIR:-$ROOT/work}"
[ -d "$SRC" ] || { echo "run tools/shared/oss/freetype/build.sh first" >&2; exit 2; }
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
T="$B/ft_mt"; rm -rf "$T"; mkdir -p "$T"; cp -r "$SRC" "$T/src"; chmod -R u+w "$T/src"
(cd "$T/src" && emmake make clean >/dev/null 2>&1; EMCC_CFLAGS="-pthread" emmake make -j4 >/dev/null 2>&1)   # CFLAGS は上書きしない (unix-cc.mk の CFLAGS は -c を含む)
LIB="$T/src/objs/.libs/libfreetype.a"; [ -f "$LIB" ] || { echo "FAIL: wasm pthread libfreetype.a not built" >&2; exit 1; }
INC=(-I "$ROOT/include" -I "$ROOT/src" -I "$FTW/src/freetype-2.7/include")
gcc -O1 -w "${INC[@]}" -pthread "$HERE/ft_engine_dump.c" "$ROOT/src/gui_ft.c" "$FTW/build/freetype/native/src/objs/.libs/libfreetype.a" -o "$B/ft_dump_native" -lm
emcc -O1 -w -pthread "${INC[@]}" "$HERE/ft_engine_dump.c" "$ROOT/src/gui_ft.c" "$LIB" -o "$B/ft_dump_wasm.cjs" \
  -sENVIRONMENT=node -sNODERAWFS=1 -sEXIT_RUNTIME=1 -sINITIAL_MEMORY=67108864 -sSTACK_SIZE=1048576 -lm
"$B/ft_dump_native" "$FONTDIR" > "$B/ft_dump_native.txt"
node "$B/ft_dump_wasm.cjs" "$FONTDIR" > "$B/ft_dump_wasm.txt"
[ "$(wc -l < "$B/ft_dump_native.txt")" -ge 11 ] || { echo "FAIL: dump too short"; exit 1; }
cmp "$B/ft_dump_native.txt" "$B/ft_dump_wasm.txt" || { diff "$B/ft_dump_native.txt" "$B/ft_dump_wasm.txt" | head -5; echo "[ft-wasm] FAIL"; exit 1; }
sed '3s/adv=/adv=9/' "$B/ft_dump_wasm.txt" > "$B/ft_dump_tamper.txt"
if cmp -s "$B/ft_dump_native.txt" "$B/ft_dump_tamper.txt"; then echo "NEGCTL FAIL: tampered dump accepted"; exit 1; else echo "negctl OK: tampered wasm dump rejected"; fi
echo "[ft-wasm] PASS native == wasm32 ($(wc -l < "$B/ft_dump_wasm.txt") lines, $(tail -1 "$B/ft_dump_wasm.txt"))"
