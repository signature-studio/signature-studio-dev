#!/usr/bin/env bash
# #537: 間接呼出の到達先候補を root に加えた推移閉包 (Delphi 殻 7 本) の算出 → lift → 判定を 1 コマンドで再現する。
#   bash tools/plugins/sampler/indirect_e2e.sh [--skip-lift]
#   --skip-lift: work/sampler/indirectlift/status_run.csv を再判定するだけ (lift しない。 ネガコン用)
# 手順: 前提 (sampler_e2e.sh の inventory + 閉包 + unreached.json。 無ければ生成) → closure_indirect.py (4 検査) → indirect_lift.sh
#       → **judge.py shells (不合格で exit 1)** → 最終行 OK
# 判定 = sampler_e2e.sh と同じ judge.py shells・同じ許容 (targets.py)。 lift_rc / emcc_c_rc / f80 が 0、未実装 helper は許容内、全 7 block に行があること。
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
  python3 lift/plugin_closure.py "${BLOCKS[@]}" > /dev/null
  python3 sampler/unreached_unique.py > work/sampler/unreached.stdout.md
  python3 sampler/closure_indirect.py | tee work/sampler/indirect.stdout.md
  bash sampler/indirect_lift.sh "${BLOCKS[@]}"
fi

CSV=work/sampler/indirectlift/status_run.csv
python3 sampler/judge.py shells "$CSV" --blocks "$BL" --allow-unimpl "$ALLOW" --allow-names "$NAMES" --out work/sampler/indirectlift/status.csv
python3 sampler/indirect_defs.py
echo "[indirect_e2e] OK: work/sampler/{indirect.json,indirectlift/status.csv}"
