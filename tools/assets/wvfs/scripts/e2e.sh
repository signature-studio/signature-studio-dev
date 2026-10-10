#!/usr/bin/env bash
# wvfs (書込可能 OPFS VFS, RT-5 / CAB-123) の 1 コマンド検収。
#   bash wvfs/scripts/e2e.sh [--fresh]
# 前提: node >= 24 (TypeScript 直実行), google-chrome, /opt/emsdk (node probe の emcc), npm i (esbuild)。
# 構成: node 単体 (63 checks) → Emscripten adapter probe (emcc, node) → Chrome OPFS e2e
#       (実ディスクプロファイル wvfs/work/chrome-profiles/, 3 起動: seed → verify+torn+compact → verify2)
set -euo pipefail
cd "$(dirname "$0")/../.."   # tools/assets (script は wvfs/scripts/)
[[ -d node_modules/esbuild ]] || npm install --no-audit --no-fund --ignore-scripts >/dev/null
ARGS=""
[[ "${1:-}" == "--fresh" ]] && ARGS="--fresh"
exec node wvfs/test/wvfs-e2e.ts $ARGS
