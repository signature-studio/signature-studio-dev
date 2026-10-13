#!/usr/bin/env bash
# 1 コマンド e2e: インベントリ再生成 → 型検査 → emcc ビルド → headless Chrome で全シナリオ実行 (約 9 分, --quick で約 2 分)
# 使い方: bash tools/audio/e2e.sh [--quick]    終了コード 0 = 全 PASS
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../.." && pwd)"
. "$ROOT/tools/shared/env.sh"
export PATH="${PNPM_HOME:-$HOME/.local/share/pnpm}/bin:$PATH"
command -v node >/dev/null || { echo "node not found" >&2; exit 1; }
bash "$HERE/inventory.sh"
"$ROOT/node_modules/.bin/tsc" --noEmit -p "$ROOT/tsconfig.json"
bash "$HERE/build.sh"
node "$HERE/harness/run.mjs" "$@" --out "$HERE/results/results.json"
# IASIO COM 経由の検収 (#98): node check + COM 経由 120s soak (--quick 時は soak を省く)。asio/e2e.sh は --out を取らない
ASIO_ARGS=(); for a in "$@"; do [ "$a" = "--quick" ] && ASIO_ARGS=(--quick); done
bash "$HERE/asio/e2e.sh" "${ASIO_ARGS[@]}"
