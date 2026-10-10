#!/usr/bin/env bash
# 1 コマンド e2e: インベントリ再生成 → 型検査 → emcc ビルド → headless Chrome で全シナリオ実行 (約 9 分, --quick で約 2 分)
# 使い方: bash tools/audio/e2e.sh [--quick]    終了コード 0 = 全 PASS
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../.." && pwd)"
export PATH="/home/ubuntu/.local/share/pnpm/bin:$PATH"
command -v node >/dev/null || { echo "node not found" >&2; exit 1; }
bash "$HERE/inventory.sh"
"$ROOT/node_modules/.bin/tsc" --noEmit -p "$ROOT/tsconfig.json"
bash "$HERE/build.sh"
node "$HERE/harness/run.mjs" "$@" --out "$HERE/results/results.json"
