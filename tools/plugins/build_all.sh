#!/usr/bin/env bash
# PLUGIN_MATRIX.{json,md} を実測から再生成する (全工程 ~4 分; 16 core 共有環境では --quick で重い関数解析を再利用)
#   bash tools/plugins/build_all.sh [--quick]
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
mkdir -p work
Q="${1:-}"
python3 inventory/win_scan.py                       # 313 PE → work/win_pe_scan.json
[ -f work/nsis_blockmap.json ] || python3 inventory/nsis_names.py   # NSIS ヘッダ解析 → block↔インストール先パス
python3 inventory/mac_scan.py                       # mac 141 プラグイン / 177 Mach-O
if [ "$Q" != "--quick" ] || [ ! -d work/winfuncs ]; then python3 inventory/win_funcs.py; fi   # 関数単位 (1 分)
python3 inventory/win_unique.py > /dev/null          # framework / 固有 分類
if [ "$Q" != "--quick" ] || [ ! -f work/mac_funcs_raw.json ]; then python3 inventory/mac_funcs.py; else python3 inventory/mac_funcs.py --reuse; fi
python3 inventory/win_abi.py                         # vtable / Info 実測
if [ "$Q" != "--quick" ] || [ ! -f work/host_calls_raw.json ]; then python3 inventory/host_calls.py; else python3 inventory/host_calls.py --reuse; fi
python3 inventory/build_matrix_raw.py                # マトリクス素データ (使用頻度・プリセット・Render tests)
python3 lift/plugin_closure.py                       # DSP エントリ閉包 + framework frontier
python3 tier.py                                      # Tier 分類 → PLUGIN_MATRIX.json / .md
