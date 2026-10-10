#!/usr/bin/env bash
# 素の (patch/FORCE_INT64 無し) wasm32 FreeType 2.7 が native と何行ずれるかを測る (REPORT §3.1 の「30/40 行ずれ」の再現)
# usage: bash oss/freetype/unpatched_check.sh   (build.sh 実行後 = work/build/freetype/out_native.txt が前提)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
SRC="$ROOT/work/src/freetype-2.7"; V="$ROOT/work/build/freetype_unpatched"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
rm -rf "$V"; mkdir -p "$V"; cp -r "$SRC" "$V/src"; chmod -R u+w "$V/src"
(cd "$V/src" && CFLAGS="-O2" emconfigure ./configure --enable-static --disable-shared --without-zlib --without-bzip2 --without-png --without-harfbuzz \
   --build=x86_64-pc-linux-gnu --host=i686-pc-linux-gnu >/dev/null 2>&1 && emmake make -j8 >/dev/null 2>&1)
emcc -O2 -I"$SRC/include" "$HERE/test_ft.c" "$V/src/objs/.libs/libfreetype.a" -o "$V/t.cjs" -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1
FONT="${FONT:-/home/ubuntu/work/analysis/mac/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL/Shared/Artwork/Fonts/OpenSans-Regular.ttf}"
node "$V/t.cjs" "$FONT" > "$V/out.txt"
echo "[ft-unpatched] differing lines vs native: $(diff "$ROOT/work/build/freetype/out_native.txt" "$V/out.txt" | grep -c '^<') / $(wc -l < "$V/out.txt")"
