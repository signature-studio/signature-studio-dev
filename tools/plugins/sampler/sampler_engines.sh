#!/usr/bin/env bash
# sampler の C++ engine / 単体 DLL (targets.py の engines: Fruity Slicer 2 の engine 23664・GMS 23677) の全 .pdata lift の到達性実測。
#   bash tools/plugins/sampler/sampler_engines.sh [--collect]
# 既定: engine を **1 本ずつ逐次** に engine_lift.sh で lift し、work/sampler/engines.csv にまとめて judge.py engines で判定する。
#   (RetDec の C バックエンドは 2.1 MB の engine 1 本で 8 GiB 超・10 分超 → 15 GiB の runner で 2 本並列は余裕が無い)
#   FROM_LL="23664": そのブロックは RetDec を走らせず既存の engine<block>/e.drc.ll から後段だけ実行 (lift_from_ll.sh)
# --collect: lift せず work/sampler/engine<block>/summary.csv を集計して判定だけ行う (別プロセスで lift 済みの時)
# 判定: 計測が成立したか (judge.py engines)。 不成立なら exit 1。 emcc -c の成否は判定外 (到達性の実測値)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
read -r -a ENGINES <<< "$(python3 sampler/targets.py engines)"
EL="$(IFS=,; echo "${ENGINES[*]}")"
mkdir -p work/sampler
if [ "${1:-}" != "--collect" ]; then
  for eb in "${ENGINES[@]}"; do
    L=lift/lift_ranges.sh
    case " ${FROM_LL:-} " in *" $eb "*) L=sampler/lift_from_ll.sh ;; esac
    LIFT="$L" bash sampler/engine_lift.sh "$eb" 900 > /dev/null
  done
fi
echo "block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines" > work/sampler/engines.csv
for eb in "${ENGINES[@]}"; do
  [ -f "work/sampler/engine$eb/summary.csv" ] && cat "work/sampler/engine$eb/summary.csv" >> work/sampler/engines.csv || echo "engine $eb: summary.csv が無い" >&2
done
cat work/sampler/engines.csv work/sampler/engine*/first_errors.txt
python3 sampler/judge.py engines work/sampler/engines.csv --blocks "$EL"
echo "[sampler_engines] OK: work/sampler/engines.csv"
