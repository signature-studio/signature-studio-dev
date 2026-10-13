#!/usr/bin/env bash
# 前提 inventory (work/ 無ければ生成)。 distortion_e2e.sh が呼ぶ。 単独実行も可。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
if [ ! -d work/winfuncs ] || [ ! -f work/win_abi.json ]; then
  python3 inventory/win_scan.py
  python3 distortion/mk_blockmap.py
  python3 inventory/win_funcs.py
  python3 inventory/win_unique.py > /dev/null
  python3 inventory/win_abi.py > /dev/null
fi
[ -f work/kernel_table.json ] || python3 inventory/kernel_table.py > /dev/null
echo "[inventory] OK"
