#!/usr/bin/env bash
# fla_test (ASIO/WASAPI shim テストバイナリ) を emcc でビルドして build/web/ に配置する。
# 使い方: bash tools/audio/build.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../.." && pwd)"
OUT="$HERE/build/web"
EMSDK="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
if [ -f "$EMSDK" ]; then set +u; . "$EMSDK" >/dev/null 2>&1 || true; set -u; fi
command -v emcc >/dev/null || { echo "[audio] emcc not found" >&2; exit 1; }
. "$HERE/flags.sh"
mkdir -p "$OUT/worklets" "$OUT/js"
emcc "${FLA_CLANG_FLAGS[@]}" "${FLA_EMCC_FLAGS[@]}" \
  -I"$HERE/src" \
  "$HERE/src/flaudio.c" "$HERE/src/flasio.c" "$HERE/src/flwasapi.c" "$HERE/test/fla_test.c" \
  -o "$OUT/fla_test.js"
# JS 側: TS を ES module へトランスパイル (型検査は pnpm typecheck 側)、worklet は public/ をそのまま配置
cp "$ROOT/public/worklets/fl-audio-worklet.js" "$OUT/worklets/"
"$ROOT/node_modules/.bin/tsc" --target es2022 --module es2022 --moduleResolution bundler --skipLibCheck \
  --lib es2022,dom,dom.iterable --outDir "$OUT/js" --rootDir "$ROOT/src/runtime" --noEmit false --isolatedModules \
  --strict --ignoreConfig "$ROOT/src/runtime/audio-layout.ts" "$ROOT/src/runtime/audio-shim.ts" "$ROOT/src/runtime/audio-input.ts"
sed -i 's|from "./audio-layout"|from "./audio-layout.js"|' "$OUT/js/audio-shim.js"
cp "$HERE/test/index.html" "$HERE/test/page.mjs" "$OUT/"
echo "[audio] build OK -> $OUT"
