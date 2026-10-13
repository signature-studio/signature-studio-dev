#!/usr/bin/env bash
# アプリ組込み用テスト音 wasm (tools/audio/test/fla_test.c) をビルドし、/wasm/audio/ 配信先へハッシュ名でステージする。
#   bash tools/audio/integration/stage_app.sh
# 出力: ${RUNTIME_WASM_DIR:-tools/runtime/work/wasm}/audio/{tone.<sha12>.mjs, tone.<sha12>.wasm, manifest.json}
# glue (.js) は pthread Worker スクリプトも兼ねるため、wasm/glue 自身の名前参照をハッシュ名へ置換する (stage_wasm.mjs と同じ流儀)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../../.." && pwd)"
OUT="${RUNTIME_WASM_DIR:-$ROOT/tools/runtime/work/wasm}/audio"
bash "$ROOT/tools/audio/build.sh" >&2
SRC="$ROOT/tools/audio/build/web"
mkdir -p "$OUT"
rm -f "$OUT"/tone.*.mjs "$OUT"/tone.*.wasm
wsha="$(sha256sum "$SRC/fla_test.wasm" | cut -c1-12)"
jsha="$(sha256sum "$SRC/fla_test.js" | cut -c1-12)"
wasm="tone.$wsha.wasm"
glue="tone.$jsha.mjs"
cp "$SRC/fla_test.wasm" "$OUT/$wasm"
sed -e "s/fla_test\.wasm/$wasm/g" "$SRC/fla_test.js" > "$OUT/$glue"
if grep -q 'fla_test\.' "$OUT/$glue"; then echo "[stage_app] glue に未置換の fla_test. 参照が残っています" >&2; exit 1; fi
printf '{"glue":"%s","wasm":"%s"}\n' "$glue" "$wasm" > "$OUT/manifest.json"
echo "[stage_app] -> $OUT ($glue, $wasm)"
