#!/usr/bin/env bash
# IASIO COM アダプタ (tools/audio/asio) のテストバイナリを emcc でビルドする。
#   node check : work/node/com_check.cjs  — COM 面静的検証 (shimx をリンクし実レジストリ経由も検証)
#   web        : work/web/               — headless Chrome で FLEngine 呼出を模した全経路 (FlAudioShim 必要)
# 成果物は work/ (gitignore)。使い方: bash tools/audio/asio/build.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
AUDIO="$(cd -- "$HERE/.." && pwd)"
ROOT="$(cd -- "$AUDIO/../.." && pwd)"
OUT="$HERE/work"
EMSDK="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
if [ -f "$EMSDK" ]; then set +u; . "$EMSDK" >/dev/null 2>&1 || true; set -u; fi
command -v emcc >/dev/null || { echo "[iasio] emcc not found" >&2; exit 1; }
# tools/audio/flags.sh の流儀 (clang 警告フラグのみ借用。emcc フラグは export 違いのため下で明記)
. "$AUDIO/flags.sh"
mkdir -p "$OUT/node" "$OUT/web" "$OUT/web/js" "$OUT/web/worklets"

# --- 1) node check: COM 面 (AudioContext 不使用)。-DFLASIO_PROFILE_ILWASAPI=1 = ILWASAPI 実測値プロファイル。
#     shimx (読取専用の参照リンク) を組込み、iasio_shimx_register() 経由の実レジストリ経路を検証する。
#     shimx の実装は既定で既成オブジェクト work/obj_MT をリンク (shimx 側作業中のツリー変更に影響されない)。
#     無ければソースからビルドする (shimx が未ビルドの環境 = クリーンチェックアウト用)。
#     IASIO_FORCE_SHIMX_SRC=1 で既成オブジェクトがあってもソースからビルド (デバッグ用)。
SHIMX_OBJS=""
if [ "${IASIO_FORCE_SHIMX_SRC:-0}" != "1" ]; then
  SHIMX_OBJS=$(ls "$ROOT/tools/shimx/work/obj_MT/"*.o 2>/dev/null || true)
fi
if [ -z "$SHIMX_OBJS" ]; then
  SHIMX_OBJ="$OUT/node/shimx_obj"
  mkdir -p "$SHIMX_OBJ"
  for f in "$ROOT/tools/shimx/src/"*.c; do
    emcc -c -O2 -w -fno-strict-aliasing -pthread -I"$ROOT/tools/shimx/src" "$f" -o "$SHIMX_OBJ/$(basename "$f" .c).o"
  done
  SHIMX_OBJS="$SHIMX_OBJ"/*.o
fi
emcc "${FLA_CLANG_FLAGS[@]}" -DFLASIO_PROFILE_ILWASAPI=1 -DFLASIO_COM_SHIMX=1 \
  -I"$AUDIO/src" -I"$HERE" -I"$ROOT/tools/shimx/src" \
  -pthread -sPROXY_TO_PTHREAD=1 -sPTHREAD_POOL_SIZE=12 -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=67108864 \
  -sENVIRONMENT=node -sERROR_ON_UNDEFINED_SYMBOLS=1 -sSTACK_SIZE=1048576 -sEXIT_RUNTIME=1 -sGLOBAL_BASE=1048576 -sASSERTIONS=1 \
  -sEXPORTED_FUNCTIONS=_main \
  "$HERE/iasio.c" "$HERE/iasio_vreg.c" "$HERE/iasio_shimx.c" "$HERE/test/com_test.c" \
  "$AUDIO/src/flaudio.c" "$AUDIO/src/flasio.c" \
  $SHIMX_OBJS \
  -o "$OUT/node/com_check.js"
mv "$OUT/node/com_check.js" "$OUT/node/com_check.cjs"

# --- 2) web: FLEngine 呼出を模した全経路 (tools/audio build.sh と同一の emcc フラグ + 本アダプタ export)
emcc "${FLA_CLANG_FLAGS[@]}" \
  -pthread -sPROXY_TO_PTHREAD=1 -sPTHREAD_POOL_SIZE=12 -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=67108864 \
  -sENVIRONMENT=web,worker -sERROR_ON_UNDEFINED_SYMBOLS=1 -sSTACK_SIZE=1048576 -sASSERTIONS=1 \
  -Wno-pthreads-mem-growth -DFLASIO_PROFILE_ILWASAPI=1 \
  -sEXPORTED_FUNCTIONS=_main,_fla_ctl_ptr,_fla_layout_count,_fla_layout_off,_fla_layout_name,_com_test_done_ptr,_com_test_result_ptr,_flasio_tl_ptr,_flasio_tl_count,_flasio_tl2_ptr \
  -sEXPORTED_RUNTIME_METHODS=wasmMemory,UTF8ToString \
  -I"$AUDIO/src" -I"$HERE" \
  "$HERE/iasio.c" "$HERE/iasio_vreg.c" "$HERE/test/com_test.c" \
  "$AUDIO/src/flaudio.c" "$AUDIO/src/flasio.c" \
  -o "$OUT/web/com_test.js"

# JS 側: TS コントローラ (audio-shim.ts) を ES module 化 + worklet 配置 (tools/audio/build.sh と同一)
cp "$ROOT/public/worklets/fl-audio-worklet.js" "$OUT/web/worklets/"
"$ROOT/node_modules/.bin/tsc" --target es2022 --module es2022 --moduleResolution bundler --skipLibCheck \
  --lib es2022,dom,dom.iterable --outDir "$OUT/web/js" --rootDir "$ROOT/src/runtime" --noEmit false --isolatedModules \
  --strict --ignoreConfig "$ROOT/src/runtime/audio-layout.ts" "$ROOT/src/runtime/audio-shim.ts"
sed -i 's|from "./audio-layout"|from "./audio-layout.js"|' "$OUT/web/js/audio-shim.js"
cp "$HERE/harness/index_com.html" "$HERE/harness/com_page.mjs" "$HERE/harness/chunk_verify.mjs" "$OUT/web/"
echo "[iasio] build OK -> $OUT"
