#!/usr/bin/env bash
# AU-9 e2e: コミット済み HEAD の src/ ・public/ を一時ディレクトリへ展開 → index.ts.diff を適用 → typecheck → vite build →
# headless Chrome で「クリック → FlAudioShim 経由のテスト音 (440/660Hz 正弦) 再生」を検証する (dev / preview(本番ビルド) 両方)。
#   bash tools/audio/integration/e2e.sh        終了コード 0 = 全 PASS
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../../.." && pwd)"
# shellcheck source=/dev/null
. "$ROOT/tools/shared/env.sh"
TMP="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/au9_verify"
rm -rf "$TMP"; mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT

# 1) 検証対象 = コミット済み HEAD (未コミット WIP に依存しない)
git -C "$ROOT" archive HEAD | tar -x -C "$TMP"
ln -s "$ROOT/node_modules" "$TMP/node_modules"
if grep -q "startFlAudio" "$TMP/src/index.ts"; then echo "[au9] index.ts は適用済み (パッチ省略)"; else ( cd "$TMP" && patch -p1 --no-backup-if-mismatch < "$ROOT/tools/audio/integration/index.ts.diff" ); fi

# 2) テスト音 wasm を stage (RUNTIME_WASM_DIR は vite.config.ts の /wasm/* 配信元)
export RUNTIME_WASM_DIR="$TMP/wasm"
bash "$HERE/stage_app.sh"

# 3) typecheck + build (パッチ適用後)
( cd "$TMP" && "$ROOT/node_modules/.bin/tsc" --noEmit && echo "[au9] typecheck OK (patched)" )
( cd "$TMP" && "$ROOT/node_modules/.bin/vite" build --logLevel warn && echo "[au9] vite build OK" && ls dist/worklets )

# 失敗ログを残す (tools/audio/work/ は gitignore)。終了コードは node の値をそのまま返す
LOG_DIR="$ROOT/tools/audio/work"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/e2e_last.log"
set +e
AU9_ROOT="$TMP" node "$HERE/e2e.mjs" "$@" 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
set -e
echo "[au9] log -> $LOG (exit=$rc)"
exit "$rc"
