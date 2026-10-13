#!/usr/bin/env bash
# #200 (PM 指示): dynamics 7 閉包に間接呼出到達先 (sampler #537 の closure_indirect 定義) を加えた推移閉包の算出 → lift → 判定を 1 コマンドで再現する。
#   bash tools/plugins/dynamics/indirect_e2e.sh
# 手順: 前提 (dynamics_e2e.sh の inventory + 閉包。 無ければ生成) → closure_indirect.py (4 検査) → indirect_lift.sh (7 本)
#       → judge.py (lift_rc / declares_unimpl / f80 / emcc_c_rc が全 0 で合格。 不合格・行欠落で exit 1)
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

python3 lift/plugin_closure.py "${BLOCKS[@]}" > /dev/null
python3 dynamics/closure_indirect.py | tee work/dynamics/indirect.stdout.md
bash dynamics/indirect_lift.sh "${BLOCKS[@]}"

rc=0; python3 dynamics/judge.py work/dynamics/indirectlift/status_run.csv "${BLOCKS[@]}" -o work/dynamics/indirectlift/status.csv || rc=$?
[ "$rc" = 0 ] || { echo "[dynamics_indirect_e2e] FAIL: 判定が不合格 (judge.py rc=$rc)" >&2; exit "$rc"; }
echo "[dynamics_indirect_e2e] OK: work/dynamics/{indirect.json,indirectlift/status.csv}"
