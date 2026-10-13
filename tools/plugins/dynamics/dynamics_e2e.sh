#!/usr/bin/env bash
# PLG-F3 (#200) dynamics 7 本の「lift 前提」実測を 1 コマンドで再現する。
#   bash tools/plugins/dynamics/dynamics_e2e.sh [--skip-lift]
# 手順: 前提 inventory (work/ 無ければ生成) → 7 閉包 → batch_lift (RetDec+pass 鎖 → emcc -c) → 判定 → closure_facts.py → engine 2 本の lift (参考)
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

python3 - "${BLOCKS[@]}" <<'PY'
import csv, sys
want = set(sys.argv[1:])
rows = [r for r in csv.reader(open('work/batch/status.csv'))]
last = {r[0]: r for r in rows[1:] if r[0] in want}   # 再実行時は最後の行を採用
hdr, body = rows[0], list(last.values())
csv.writer(open('work/dynamics/status7.csv', 'w')).writerows([hdr] + body)
bad = [r for r in body if r[4] != '0' or r[8] != '0' or r[7] != '0']
print('status7: %d rows; lift_rc!=0 / f80!=0 / emcc_c!=0: %d' % (len(body), len(bad)))
for r in bad:
    print('  ', r)
sys.exit(0 if len(body) == len(want) else 1)
PY

python3 dynamics/closure_facts.py > work/dynamics/facts.stdout.json 2> work/dynamics/facts.err
python3 dynamics/matrix_check.py

# engine 分離型 2 本の C++ engine DLL (判定には含めない: 到達性の実測のみ)
if [ "${1:-}" != "--skip-lift" ]; then
  echo "block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines" > work/dynamics/engines.csv
  for eb in 19252 19048; do bash dynamics/engine_lift.sh "$eb" 1500 | tail -n 1 >> work/dynamics/engines.csv; done
  cat work/dynamics/engines.csv work/dynamics/engine*/first_errors.txt
fi
echo "[dynamics_e2e] OK: work/dynamics/{status7.csv,facts.json}"
