#!/usr/bin/env bash
# 1 コマンド E2E: 復元パス → インベントリ → ブートセット → パッケージ → node/Chrome テスト → 実測
#   bash e2e.sh [--full]      既定: 小サブセット (数十秒)。--full: 全ツリー(約 100 秒の圧縮 + 全テスト)
# 前提: node >= 24 (TypeScript をそのまま実行), python3, google-chrome, npm i (esbuild)。素材は analysis/ 配下。
set -euo pipefail
cd "$(dirname "$0")"
FULL=0; [[ "${1:-}" == "--full" ]] && FULL=1
export PATH="${PATH}:/home/ubuntu/.local/share/pnpm/bin"
[[ -d node_modules/esbuild ]] || npm install --no-audit --no-fund --ignore-scripts >/dev/null
mkdir -p work
EXE="${FL_WIN_INSTALLER:-$HOME/ダウンロード/flstudio_win64_26.1.7.5653.exe}"
[[ -f work/win_paths.json ]] || python3 win_paths/recover_paths.py "$EXE" /home/ubuntu/work/analysis/win64/block_manifest.json work/win_paths.json
[[ -f work/inv_win.jsonl ]] || python3 inventory/inventory.py
python3 bootset/strings_scan.py >/dev/null
python3 bootset/classify_bootset.py >/dev/null
../../node_modules/.bin/tsc -p tsconfig.json --noEmit
if [[ $FULL == 1 ]]; then PKG=work/pkg-full; node pack/pack.ts --out $PKG | tail -5
else PKG=work/pkg-small; node pack/pack.ts --only '^(Data/System/[^/]*$|Artwork/|System/Config/|Data/Templates/Minimal/)' --out $PKG | tail -3; fi
node test/node-test.ts --pkg $PKG --out work/results-node.json
node test/emscripten-test.ts --pkg $PKG
node test/browser-test.ts --pkg $PKG --out work/results-chrome.json
[[ $FULL == 1 ]] && node test/bench.ts --pkg $PKG --out work/bench-net.json
# 314MB 級 wasm asset (tools/perf/work/huge/k100.wasm) の二段キャッシュ + compileStreaming e2e
node test/asset-e2e.ts
echo "E2E OK"
