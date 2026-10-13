#!/usr/bin/env bash
# 前提 work/ (gitignore) の生成。 既にあるものは作り直さない。 g1_e2e.sh が呼ぶ。
#   win_funcs.py は 4 core で数分〜十数分かかる (全 FP_DelphiPlug DLL の関数ハッシュ; plugin_closure.py の framework 判定に必要)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
[ -f work/win_pe_scan.json ] || python3 inventory/win_scan.py
[ -f work/nsis_blockmap.json ] || python3 g1/mk_blockmap.py
[ -d work/winfuncs ] || python3 inventory/win_funcs.py
[ -f work/win_unique.json ] || python3 inventory/win_unique.py > /dev/null
[ -f work/win_abi.json ] || python3 inventory/win_abi.py > /dev/null
[ -f work/kernel_table.json ] || python3 inventory/kernel_table.py > /dev/null
echo "[prep] OK"
