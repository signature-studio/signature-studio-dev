#!/usr/bin/env bash
# PLG-F1 (#198) 1 コマンド再現: 素材展開 → inventory (無ければ) → 9 本 batch lift → Eff_Render 経路計画 → 脱落 call 監査 → Phase Inverter / Mute 2 差分試験
#   bash tools/plugins/f1/f1_e2e.sh          (Actions: oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk)
# inventory (win_funcs.py) は 4 core で 8 分弱かかる。 work/winfuncs が既にあれば再利用する。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
source "$HERE/env.sh"
BLOCKS="18983 18988 19049 19056 19065 19076 19084 19085 19250"
cd "$ROOT"
mkdir -p work
if [ ! -f work/win_pe_scan.json ]; then python3 inventory/win_scan.py; fi
if [ ! -f work/nsis_blockmap.json ]; then python3 inventory/blockmap_from_matrix.py; fi
if [ ! -d work/winfuncs ] || [ "$(ls work/winfuncs | wc -l)" -lt 180 ]; then python3 inventory/win_funcs.py; fi
if [ ! -f work/win_abi.json ]; then python3 inventory/win_abi.py; fi
rm -f work/batch/status.csv
t0=$(date +%s)
bash lift/batch_lift.sh $BLOCKS
echo "[f1] batch lift 9 本: $(( $(date +%s) - t0 )) s, load $(cut -d' ' -f1-3 /proc/loadavg)"
python3 f1/f1_plan.py $BLOCKS
python3 f1/f1_call_audit.py $BLOCKS
bash f1/pi/pi_e2e.sh
bash f1/mute/mute_e2e.sh
