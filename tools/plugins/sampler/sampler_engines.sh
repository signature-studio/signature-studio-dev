#!/usr/bin/env bash
# sampler の C++ engine / 単体 DLL (targets.py の engines: Fruity Slicer 2 の engine 23664・GMS 23677) の全 .pdata lift の到達性実測。
#   bash tools/plugins/sampler/sampler_engines.sh [--collect]
# 既定: engine を 2 本並列に lift_from_ll.sh (RetDec は .ll 書き出し後に止める → 後段 pass 鎖) → emcc -c で lift し、
#   work/sampler/engines.csv にまとめて judge.py engines で判定する。 RetDec の C バックエンドを待つ lift_ranges.sh 直行は
#   Fruity Slicer 2 の engine 1 本で 10 分超・8 GiB 超 (REPORT §5) のため使わない。 FULL_RETDEC=1 なら lift_ranges.sh を使う (逐次実行を推奨)
# --collect: lift せず work/sampler/engine<block>/summary.csv を集計して判定だけ行う (別プロセスで lift 済みの時)
# 判定 (judge.py engines): lift_rc 0 / define>0 / 最終 IR の emcc -c rc 0 (emcc_c_rc_after_f80) / missing_ref 0。 1 件でも不合格なら exit 1
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
read -r -a ENGINES <<< "$(python3 sampler/targets.py engines)"
EL="$(IFS=,; echo "${ENGINES[*]}")"
mkdir -p work/sampler
if [ "${1:-}" != "--collect" ]; then
  L=sampler/lift_from_ll.sh; [ "${FULL_RETDEC:-0}" = 1 ] && L=lift/lift_ranges.sh
  for eb in "${ENGINES[@]}"; do
    rm -rf "work/sampler/engine$eb"
    ( LIFT="$L" bash sampler/engine_lift.sh "$eb" 900 > /dev/null ) &
    [ "${FULL_RETDEC:-0}" = 1 ] && wait
  done
  wait
fi
echo "block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines,emcc_c_rc_after_f80" > work/sampler/engines.csv
for eb in "${ENGINES[@]}"; do
  [ -f "work/sampler/engine$eb/summary.csv" ] && cat "work/sampler/engine$eb/summary.csv" >> work/sampler/engines.csv || echo "engine $eb: summary.csv が無い" >&2
done
cat work/sampler/engines.csv work/sampler/engine*/first_errors.txt
python3 sampler/judge.py engines work/sampler/engines.csv --blocks "$EL"
echo "[sampler_engines] OK: work/sampler/engines.csv"
