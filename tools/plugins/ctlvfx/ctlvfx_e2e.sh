#!/usr/bin/env bash
# PLG-F8 (#205) 28 本 (controller / VFX / gui-only / visual 他) の「lift 前提」実測を 1 コマンドで再現する。
#   bash tools/plugins/ctlvfx/ctlvfx_e2e.sh [--skip-lift]            全工程
#   bash tools/plugins/ctlvfx/ctlvfx_e2e.sh --judge-only <status.csv>  判定 (judge.py) だけ。 ネガティブコントロール用
# 手順: 前提 inventory (work/ 無ければ生成) → 28 閉包 → batch_lift (RetDec+pass 鎖 → emcc -c) → [gate] judge.py → closure_facts.py
#        → [gate] matrix_check.py → [gate] ids_crosscheck.py → engine 2 本の lift (参考; gate に含めない)
# exit: gate (judge / matrix_check / ids_crosscheck) が 1 つでも不合格なら非 0。 `[ctlvfx_e2e] OK` は全 gate 合格時のみ出る。
#       gate は全部走らせてから結果をまとめて返す (不合格でも他の実測値は残す)。
# 出力: work/ctlvfx/{status.csv,facts.json,engines.csv} (work/ は gitignore)
# 前提素材: fl-win64 / toolchain-retdec (/opt/retdec) / toolchain-emsdk (/opt/emsdk)  (docs/WORKFLOW.md §11)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."

if [ "${1:-}" = "--judge-only" ]; then
  [ -n "${2:-}" ] || { echo "usage: $0 --judge-only <status.csv>" >&2; exit 2; }
  python3 ctlvfx/judge.py "$2" || { echo "[ctlvfx_e2e] FAIL: judge" >&2; exit 1; }
  echo "[ctlvfx_e2e] OK (judge-only)"
  exit 0
fi

read -ra BLOCKS < <(python3 ctlvfx/targets.py blocks)
read -ra ENGINES < <(python3 - <<'PY'
import sys
sys.path.insert(0, 'ctlvfx')
from targets import TARGETS
print(' '.join(str(e) for _, _, _, e in TARGETS if e))
PY
)
mkdir -p work/ctlvfx

if [ ! -d work/winfuncs ] || [ ! -f work/win_abi.json ]; then
  python3 inventory/win_scan.py
  python3 ctlvfx/mk_blockmap.py
  python3 inventory/win_funcs.py
  python3 inventory/win_unique.py > /dev/null
  python3 inventory/win_abi.py > /dev/null
fi
[ -f work/kernel_table.json ] || python3 inventory/kernel_table.py > /dev/null

python3 lift/plugin_closure.py "${BLOCKS[@]}"
if [ "${1:-}" != "--skip-lift" ]; then
  n0=1; [ -f work/batch/status.csv ] && n0=$(wc -l < work/batch/status.csv)
  bash lift/batch_lift.sh "${BLOCKS[@]}"
else
  n0=1   # --skip-lift は既存 status.csv の行をそのまま使う (古い行を拾いうる)
  echo "[ctlvfx_e2e] --skip-lift: work/batch/status.csv の既存行を使用"
fi
# 今回の実行で追記された行だけを判定に回す (lift が行を書かずに落ちた block を、過去の合格行で通さないため)
{ head -n 1 work/batch/status.csv; tail -n +$((n0 + 1)) work/batch/status.csv; } > work/ctlvfx/status.csv

FAILED=()
python3 ctlvfx/judge.py work/ctlvfx/status.csv || FAILED+=(judge)

python3 ctlvfx/closure_facts.py > work/ctlvfx/facts.stdout.json 2> work/ctlvfx/facts.err
python3 ctlvfx/matrix_check.py || FAILED+=(matrix_check)
python3 ctlvfx/ids_crosscheck.py || FAILED+=(ids_crosscheck)

# engine 分離型 2 本の C++ engine DLL (gate に含めない: 到達性の実測のみ)
if [ "${1:-}" != "--skip-lift" ]; then
  echo "block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines" > work/ctlvfx/engines.csv
  for eb in "${ENGINES[@]}"; do bash ctlvfx/engine_lift.sh "$eb" 1500 | tail -n 1 >> work/ctlvfx/engines.csv; done
  cat work/ctlvfx/engines.csv work/ctlvfx/engine*/first_errors.txt
fi

if [ "${#FAILED[@]}" -ne 0 ]; then
  echo "[ctlvfx_e2e] FAIL: ${FAILED[*]}" >&2
  exit 1
fi
echo "[ctlvfx_e2e] OK: work/ctlvfx/{status.csv,facts.json}"
