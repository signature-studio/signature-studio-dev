#!/usr/bin/env bash
# FreeType 2.7 を upstream ソースから (a) native gcc, (b) emscripten wasm32, (c) emscripten wasm64 で再ビルドし、
# 同一テストハーネス (test_ft.c) の出力を比較する。 usage: bash oss/freetype/build.sh
#
# 重要 (REPORT.md §3.1): FreeType 2.7 の ftgrays.c は FT_UDIV (近似除算) が `long` 幅に依存する。
#  元バイナリ (x86_64 LP64) と bit 一致させるには long=64bit が必要:
#   - wasm32 (long=32bit): (1) ftoption.h の FT_CONFIG_OPTION_FORCE_INT64 を有効化して FT_LONG64 経路
#     (= LP64 と同じ rasterizer 実装; 未定義だと別実装になりピクセルが 1LSB ずれる) を選ばせ、
#     (2) FT_UDIV を long long 化する patch (oss/freetype/ftgrays_lp64.patch) を当てる
#   - wasm64 (-sMEMORY64=1, long=64bit): 無改変で一致
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
source "$ROOT/env.sh"
SRC="$ROOT/work/src/freetype-2.7"; B="$ROOT/work/build/freetype"
[ -d "$SRC" ] || bash "$ROOT/oss/fetch_sources.sh"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
rm -rf "$B"; mkdir -p "$B"
CFG="--enable-static --disable-shared --without-zlib --without-bzip2 --without-png --without-harfbuzz"
prep() { mkdir -p "$B/$1"; cp -r "$SRC"/. "$B/$1/src"; chmod -R u+w "$B/$1/src"; }

echo "[ft] native (gcc) configure+make"
prep native; (cd "$B/native/src" && ./configure $CFG >/dev/null 2>&1 && make -j8 >/dev/null 2>&1)

wasm_build() { # name extra_cflags patch(0/1)
  echo "[ft] $1 configure+make (emcc $(emcc --version | head -1 | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' | head -1), flags: $2)"
  prep "$1"
  if [ "$3" = 1 ]; then
    (cd "$B/$1/src" && patch -p1 -s < "$HERE/ftgrays_lp64.patch" \
       && sed -i 's/^#undef FT_CONFIG_OPTION_FORCE_INT64/#define FT_CONFIG_OPTION_FORCE_INT64/' include/freetype/config/ftoption.h)
  fi
  # config.sub が emscripten を知らないため i686 を名乗らせて cross 扱いにする (ビルド成果物は emcc 製)
  (cd "$B/$1/src" && CFLAGS="-O2 $2" emconfigure ./configure $CFG --build=x86_64-pc-linux-gnu --host=i686-pc-linux-gnu >/dev/null 2>"$B/$1.configure.err" \
     && emmake make -j8 >/dev/null 2>&1)
}
wasm_build wasm32 "" 1
wasm_build wasm64 "-sMEMORY64=1" 0

echo "[ft] test harness"
INC="$SRC/include"
gcc -O2 -I"$INC" "$HERE/test_ft.c" "$B/native/src/objs/.libs/libfreetype.a" -lm -o "$B/test_native"
emcc -O2 -I"$INC" "$HERE/test_ft.c" "$B/wasm32/src/objs/.libs/libfreetype.a" -o "$B/test_wasm32.cjs" \
  -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1
emcc -O2 -sMEMORY64=1 -I"$INC" "$HERE/test_ft.c" "$B/wasm64/src/objs/.libs/libfreetype.a" -o "$B/test_wasm64.cjs" \
  -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1
echo "[ft] sizes: libfreetype.a native=$(stat -c %s "$B/native/src/objs/.libs/libfreetype.a") wasm32=$(stat -c %s "$B/wasm32/src/objs/.libs/libfreetype.a")  test wasm32=$(stat -c %s "$B/test_wasm32.wasm") wasm64=$(stat -c %s "$B/test_wasm64.wasm")"

FONT="${FONT:-$FL_MAC_DIR/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL/Shared/Artwork/Fonts/OpenSans-Regular.ttf}"
"$B/test_native" "$FONT" > "$B/out_native.txt"
node "$B/test_wasm32.cjs" "$FONT" > "$B/out_wasm32.txt"
node64="${EMSDK_NODE:-node}"   # wasm64 (table64) は node >= 24 が必要。システム node v22 では CompileError (emsdk 同梱 node を使う)
"$node64" "$B/test_wasm64.cjs" "$FONT" > "$B/out_wasm64.txt" 2>"$B/out_wasm64.err"
rc=0
for v in wasm32 wasm64; do
  if diff -q "$B/out_native.txt" "$B/out_$v.txt" >/dev/null; then
    echo "[ft] PASS $v: native == wasm ($(wc -l < "$B/out_$v.txt") lines, $(tail -1 "$B/out_$v.txt"))"
  else diff "$B/out_native.txt" "$B/out_$v.txt" | head -6; echo "[ft] FAIL $v"; rc=1; fi
done

# LGL-3 (#86): 再ビルド記録 (upstream 版・ソース sha256・configure 引数・パッチ) を NOTICES 用に書く
if [ "$rc" = 0 ]; then
  node "$ROOT/../legal/notices/record.mjs" --id freetype-2.7 --name FreeType --version 2.7 --license-spdx FTL \
    --url https://download.savannah.gnu.org/releases/freetype/freetype-2.7.tar.gz --archive "$ROOT/work/src/freetype-2.7.tar.gz" \
    --src-dir "$SRC" --license-file docs/FTL.TXT --license-file docs/LICENSE.TXT \
    --script "$HERE/build.sh" --toolchain emcc --target wasm32 --target wasm64 \
    --step "configure=./configure $CFG --build=x86_64-pc-linux-gnu --host=i686-pc-linux-gnu (emconfigure, CFLAGS=-O2; wasm64 は CFLAGS=-O2 -sMEMORY64=1)" \
    --step "config-edit=wasm32 のみ include/freetype/config/ftoption.h の FT_CONFIG_OPTION_FORCE_INT64 を #define" \
    --patch "tools/shared/oss/freetype/ftgrays_lp64.patch:ftgrays.c の FT_UDIV を long long 化 (wasm32 のみ)"
fi
exit $rc
