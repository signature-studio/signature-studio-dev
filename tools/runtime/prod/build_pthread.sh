#!/usr/bin/env bash
# RT-2: 本番 emcc フラグ (flags.sh) で shim MT + boot_main.c を pthread ビルドする。
#   bash tools/runtime/prod/build_pthread.sh            → tools/runtime/work/prod/fl-mt.{mjs,wasm}
#   MT_NEG=1 bash ...                                   → ネガティブコントロール版 (非 atomic カウンタ)
#   PROD_POOL=N bash ...                                → PTHREAD_POOL_SIZE を変更
# emsdk は /opt/emsdk (EMSDK_ENV で変更可)。キャッシュが読み取り専用なら EM_CACHE を書込可能な場所へ複製する。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../../.." && pwd)"
OUT="${PROD_OUT:-$ROOT/tools/runtime/work/prod}"
EMSDK="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"

if [ -f "$EMSDK" ]; then set +u; . "$EMSDK" >/dev/null 2>&1 || true; set -u; fi
command -v emcc >/dev/null || { echo "[prod] emcc が見つかりません (toolchain-emsdk 素材 / EMSDK_ENV)" >&2; exit 1; }

if [ -z "${EM_CACHE:-}" ]; then
  EMROOT="$(dirname "$(readlink -f "$(command -v emcc)")")"
  if [ ! -w "$EMROOT/cache" ]; then
    export EM_CACHE="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/em_cache"
    mkdir -p "$EM_CACHE"
    [ -n "$(ls -A "$EM_CACHE" 2>/dev/null)" ] || cp -a "$EMROOT/cache/." "$EM_CACHE/"
    echo "[prod] EM_CACHE=$EM_CACHE (emsdk cache は読み取り専用)"
  fi
fi

source "$HERE/flags.sh"
mkdir -p "$OUT/obj"
NEG=()
[ "${MT_NEG:-0}" = "1" ] && NEG=(-DMT_NEG)

# shim/test_main.c の main を衝突しない名前にして取り込む
emcc "${PROD_CLANG_FLAGS[@]}" -pthread -Dmain=shim_selftest_main -c "$ROOT/tools/shim/test/test_main.c" -o "$OUT/obj/test_main.o"
emcc "${PROD_CLANG_FLAGS[@]}" -pthread "${NEG[@]}" -c "$HERE/boot_main.c" -o "$OUT/obj/boot_main.o"
for f in "$ROOT"/tools/shim/src/*.c; do
  emcc "${PROD_CLANG_FLAGS[@]}" -pthread -c "$f" -o "$OUT/obj/$(basename "${f%.c}").o"
done
emcc "${PROD_CLANG_FLAGS[@]}" "${PROD_EMCC_FLAGS[@]}" "$OUT"/obj/*.o -o "$OUT/fl-mt.mjs"
rm -rf "$OUT/obj"
echo "[prod] emcc $(emcc --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1) pool=${PROD_POOL:-12} neg=${MT_NEG:-0}"
ls -l "$OUT/fl-mt.mjs" "$OUT/fl-mt.wasm"
