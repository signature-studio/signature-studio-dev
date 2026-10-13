#!/usr/bin/env bash
# 前提 inventory (tools/plugins/work/, gitignore) を無ければ生成する。 win_funcs.py は 4 core で数分かかる。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
[ -f work/win_pe_scan.json ] || python3 inventory/win_scan.py
[ -f work/nsis_blockmap.json ] || python3 f2/mk_blockmap.py
[ -d work/winfuncs ] || python3 inventory/win_funcs.py
[ -f work/win_unique.json ] || python3 inventory/win_unique.py > /dev/null
[ -f work/win_abi.json ] || python3 inventory/win_abi.py > /dev/null
[ -f work/kernel_table.json ] || python3 inventory/kernel_table.py > /dev/null
