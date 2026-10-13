#!/usr/bin/env bash
# stdbuild_e2e.sh — 標準ビルド設定 + 署名ガード (PERF-P1 / #155) の 1 コマンド検証。plugin バイナリ・RetDec 不要 (合成 lift IR / C)。
#   bash tools/liftlib/stdbuild_e2e.sh [WORKDIR]      exit 0 = ALL PASS。WORKDIR は存在しない dir のみ (既存 dir は消さず拒否)。省略時は work/stdbuild_test を作り直す
# 前提: emsdk (EMSDK_DIR, 既定 /opt/emsdk) / node / python capstone,pefile (liftlib.pipeline の import 用)
# 内容は tests/test_stdbuild.py の docstring を参照 (U 設定 / S pipeline 全変種 + ネガコン / C x64c 形 C ビルド + CLI guard / N fail-open 封じ込め)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
[ -f "${EMSDK_DIR:-/opt/emsdk}/emsdk_env.sh" ] || { echo "[stdbuild_e2e] emsdk 無し (toolchain-emsdk / EMSDK_DIR)" >&2; exit 2; }
python3 -c "import capstone, pefile" 2>/dev/null || { echo "[stdbuild_e2e] python: capstone/pefile が必要 (pip install capstone pefile)" >&2; exit 2; }
source "${EMSDK_DIR:-/opt/emsdk}/emsdk_env.sh" >/dev/null 2>&1
T0=$(date +%s)
echo "[stdbuild_e2e] load(start) $(cut -d' ' -f1-3 /proc/loadavg)"
python3 "$HERE/tests/test_stdbuild.py" "$@"
echo "[stdbuild_e2e] load(end) $(cut -d' ' -f1-3 /proc/loadavg) / elapsed $(( $(date +%s) - T0 )) s"
