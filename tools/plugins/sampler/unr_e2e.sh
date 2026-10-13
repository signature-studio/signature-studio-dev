#!/usr/bin/env bash
# #667: total2 外の非共通関数の参照の種類 (RVA32 表・命令内即値・outside からの call/jmp・lea) の分類と、到達しうる根を足した閉包 total3 の算出 → lift → 判定 → range 欠落監査を 1 コマンドで再現する。
#   bash tools/plugins/sampler/unr_e2e.sh [--skip-lift]
#   --skip-lift: work/sampler/unrlift/status_run.csv を再判定するだけ (lift しない。 ネガコン用)
# 手順: 前提 (inventory + 閉包 + unreached.json + closure_indirect.py + closure_lea.py。 無ければ生成) → closure_unreached.py (5 検査)
#       → unr_lift.sh → **judge.py shells (不合格で exit 1)** → indirect_defs.py (range 欠落監査、total3 の ranges に対して) → 最終行 OK
# 判定 = lea_e2e.sh と同じ judge.py shells・同じ許容 (targets.py)。 どの段が不合格でも exit 1 (set -e)。 最終行の OK は全段を通った時だけ出る。
# 前提素材: fl-win64 / toolchain-retdec / toolchain-emsdk (docs/WORKFLOW.md §11)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
read -r -a BLOCKS <<< "$(python3 sampler/targets.py blocks)"
BL="$(IFS=,; echo "${BLOCKS[*]}")"
ALLOW="$(python3 sampler/targets.py allow-unimpl)"
NAMES="$(python3 -c 'import sys; sys.path.insert(0, "sampler"); import targets; print(",".join(targets.ALLOW_UNIMPL_NAMES))')"
SKIP=0
for a in "$@"; do
  case "$a" in --skip-lift) SKIP=1 ;; *) echo "usage: $0 [--skip-lift]" >&2; exit 2 ;; esac
done
mkdir -p work/sampler

if [ "$SKIP" = 0 ]; then
  if [ ! -d work/winfuncs ] || [ ! -f work/win_abi.json ]; then
    python3 inventory/win_scan.py
    python3 sampler/mk_blockmap.py
    python3 inventory/win_funcs.py
    python3 inventory/win_unique.py > /dev/null
    python3 inventory/win_abi.py > /dev/null
  fi
  [ -f work/kernel_table.json ] || python3 inventory/kernel_table.py > /dev/null
  python3 lift/plugin_closure.py "${BLOCKS[@]}" > /dev/null
  python3 sampler/unreached_unique.py > work/sampler/unreached.stdout.md
  python3 sampler/closure_indirect.py > work/sampler/indirect.stdout.md
  python3 sampler/closure_lea.py | tee work/sampler/lea.stdout.md
  python3 sampler/closure_unreached.py | tee work/sampler/unr.stdout.md
  bash sampler/unr_lift.sh "${BLOCKS[@]}"
fi

CSV=work/sampler/unrlift/status_run.csv
python3 sampler/judge.py shells "$CSV" --blocks "$BL" --allow-unimpl "$ALLOW" --allow-names "$NAMES" --out work/sampler/unrlift/status.csv
python3 sampler/indirect_defs.py --lift-dir work/sampler/unrlift --ranges-dir work/sampler/unr
echo "[unr_e2e] OK: work/sampler/{unr.json,unrlift/status.csv}"
