#!/usr/bin/env bash
# PLG-F3 (#200) dynamics 7 本の「lift 前提」実測を 1 コマンドで再現する。
#   bash tools/plugins/dynamics/dynamics_e2e.sh [--skip-lift]
# 手順: 前提 inventory (work/ 無ければ生成) → 7 閉包 → batch_lift (RetDec+pass 鎖 → emcc -c) → 判定 (judge.py) → closure_facts.py → matrix_check.py → engine 2 本の lift (参考)
# exit 0 = 判定が 7 本とも合格し、後続も完走 (不合格なら judge.py の rc で即終了し、最終の OK 行は出ない)
# 出力: work/dynamics/{status7.csv,facts.json,engines.csv} (work/ は gitignore)
# 前提素材: fl-win64 / toolchain-retdec (/opt/retdec) / toolchain-emsdk (/opt/emsdk)  (docs/WORKFLOW.md §11)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
BLOCKS=(19021 18990 19148 19245 18974 19047 19251)   # Limiter Compressor Maximus Soundgoodizer Emphasis MultibandComp TransientProc
mkdir -p work/dynamics

if [ ! -d work/winfuncs ] || [ ! -f work/win_abi.json ]; then
  python3 inventory/win_scan.py
  python3 dynamics/mk_blockmap.py
  python3 inventory/win_funcs.py
  python3 inventory/win_unique.py > /dev/null
  python3 inventory/win_abi.py > /dev/null
fi
[ -f work/kernel_table.json ] || python3 inventory/kernel_table.py > /dev/null

python3 lift/plugin_closure.py "${BLOCKS[@]}"
if [ "${1:-}" != "--skip-lift" ]; then
  bash lift/batch_lift.sh "${BLOCKS[@]}"
fi

# 判定: 7 本とも lift_rc / declares_unimpl / f80_funcs / emcc_c_rc が全 0 (不合格・行欠落 = exit 1。 dynamics/judge.py)
rc=0; python3 dynamics/judge.py work/batch/status.csv "${BLOCKS[@]}" -o work/dynamics/status7.csv || rc=$?
[ "$rc" = 0 ] || { echo "[dynamics_e2e] FAIL: 判定が不合格 (judge.py rc=$rc)" >&2; exit "$rc"; }

python3 dynamics/closure_facts.py > work/dynamics/facts.stdout.json 2> work/dynamics/facts.err
python3 dynamics/matrix_check.py

# engine 分離型 2 本の C++ engine DLL (判定には含めない: 到達性の実測のみ)
if [ "${1:-}" != "--skip-lift" ]; then
  echo "block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines" > work/dynamics/engines.csv
  for eb in 19252 19048; do bash dynamics/engine_lift.sh "$eb" 1500 | tail -n 1 >> work/dynamics/engines.csv; done
  cat work/dynamics/engines.csv work/dynamics/engine*/first_errors.txt
fi
echo "[dynamics_e2e] OK: work/dynamics/{status7.csv,facts.json}"
