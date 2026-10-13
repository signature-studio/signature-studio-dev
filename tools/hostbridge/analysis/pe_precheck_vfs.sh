#!/usr/bin/env bash
# pe_precheck_vfs.sh — HB-H17 (#787) の 1 コマンド再計算。
#   bash tools/hostbridge/analysis/pe_precheck_vfs.sh
# 前提: $HOME/artifacts/fl-win64.tar.zst (素材; block19091_PE.bin を使う) / node / python3 + pefile。
# 出力: 検査行 + SUMMARY 行。終了コード 0 = 全 PASS・ネガコン全 FAIL 検出。
set -euo pipefail
HB="$(cd -- "$(dirname -- "$0")/.." && pwd)"
ART="${ARTIFACTS_DIR:-$HOME/artifacts}"
mkdir -p "$HB/work/wrapper"
if [ ! -f "$HB/work/wrapper/extracted/block19091_PE.bin" ]; then
  (cd "$HB/work/wrapper" && tar --zstd -xf "$ART/fl-win64.tar.zst" extracted/block19091_PE.bin)
fi
cd "$HB"
node analysis/pe_precheck_vfs.mjs
