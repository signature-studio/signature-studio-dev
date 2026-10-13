#!/usr/bin/env bash
# ft_wasm_lib.sh — GUI-13 (#615): shim (pthread/atomics) と link できる wasm32 の libfreetype.a (-pthread 再ビルド) を作り、パスを stdout へ出す。
#   tools/shared/oss/freetype/build.sh が作る patch 済みツリー (work/build/freetype/wasm32/src; FORCE_INT64 + ftgrays_lp64.patch) を build/ft_mt へ複製して -pthread で再 make。
#   build/ft_mt/libfreetype.a が既にあり、元ツリーの libfreetype.a より新しければ再利用 (FT_FORCE=1 で作り直し)。進捗は stderr。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; B="$ROOT/build"; mkdir -p "$B"
FTW="$ROOT/../shared/work"; SRC="$FTW/build/freetype/wasm32/src"; T="$B/ft_mt"
[ -d "$SRC" ] || { echo "run tools/shared/oss/freetype/build.sh first (no $SRC)" >&2; exit 2; }
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v emcc >/dev/null || { echo "emcc not found" >&2; exit 2; }
LIB="$T/src/objs/.libs/libfreetype.a"
if [ "${FT_FORCE:-0}" = 1 ] || [ ! -f "$LIB" ] || [ "$SRC/objs/.libs/libfreetype.a" -nt "$LIB" ]; then
  rm -rf "$T"; mkdir -p "$T"; cp -r "$SRC" "$T/src"; chmod -R u+w "$T/src"
  (cd "$T/src" && emmake make clean >/dev/null 2>&1; EMCC_CFLAGS="-pthread" emmake make -j4 >/dev/null 2>&1)   # CFLAGS は上書きしない (unix-cc.mk の CFLAGS は -c を含む)
  echo "[ft_wasm_lib] built $LIB" >&2
fi
[ -f "$LIB" ] || { echo "FAIL: wasm pthread libfreetype.a not built" >&2; exit 1; }
echo "$LIB"
