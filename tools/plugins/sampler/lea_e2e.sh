#!/usr/bin/env bash
# #627: #537 の推移閉包に lea [rip+X] 参照の関数を root として足した閉包 (Delphi 殻 7 本) の算出 → lift → 判定 → host 呼出面・kernel 依存の再計測を 1 コマンドで再現する。
#   bash tools/plugins/sampler/lea_e2e.sh [--skip-lift]
#   --skip-lift: work/sampler/lealift/status_run.csv を再判定するだけ (lift しない。 ネガコン用)
# 手順: 前提 (inventory + 閉包 + unreached.json + closure_indirect.py。 無ければ生成) → closure_lea.py (7 検査)
#       → lea_lift.sh → **judge.py shells (不合格で exit 1)** → indirect_defs.py (range 欠落監査、total2 の ranges に対して) → facts_total.py (4 検査) → 最終行 OK
# 判定 = indirect_e2e.sh と同じ judge.py shells・同じ許容 (targets.py)。 どの段が不合格でも exit 1 (set -e)。 最終行の OK は全段を通った時だけ出る。
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
  [ -f work/sampler/facts.json ] || python3 sampler/closure_facts.py > work/sampler/facts.stdout.json 2> work/sampler/facts.err
  python3 sampler/closure_lea.py | tee work/sampler/lea.stdout.md
  bash sampler/lea_lift.sh "${BLOCKS[@]}"
fi

CSV=work/sampler/lealift/status_run.csv
python3 sampler/judge.py shells "$CSV" --blocks "$BL" --allow-unimpl "$ALLOW" --allow-names "$NAMES" --out work/sampler/lealift/status.csv
python3 sampler/indirect_defs.py --lift-dir work/sampler/lealift --ranges-dir work/sampler/lea
python3 sampler/facts_total.py | tee work/sampler/facts_total.stdout.md
echo "[lea_e2e] OK: work/sampler/{lea.json,lealift/status.csv,facts_total.json}"
