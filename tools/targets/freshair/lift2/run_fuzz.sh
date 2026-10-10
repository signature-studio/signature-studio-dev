#!/usr/bin/env bash
# run_fuzz.sh [N_STRUCTURED=200] [N_FUZZ=1000] — ctx-fuzz: 構造化 200 + ランダム 1000 試行を comp/filter 両方で
# native (実機機械語) vs wasm (mlift) bit-exact 比較 (fma0/fma1)。canary (メモリ閉込) 違反は |GUARD として行比較に含まれる。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
NS="${1:-200}"; NF="${2:-1000}"
source "$HERE/env.sh"
fail=0

for TGT in comp filter; do
  W="$HERE/work/fuzz_$TGT"; mkdir -p "$W"; cd "$W"
  python3 "$HERE/gen_fuzz_scen.py" "$TGT" fuzz_scen.txt "$NS" "$NF" >/dev/null
  N=$(wc -l < fuzz_scen.txt)
  for F in 0 1; do
    if [ "$TGT" = comp ]; then
      FA_IAT="$HERE/work/ml/iat_slots.txt" FA_POKES="$HERE/work/ml/pokes.txt" FA_DBG=1 "$HERE/work/ml/native_comp" "$CORE" fuzz_scen.txt $F > fz_n$F.txt 2> fz_n$F.err
      FA_DBG=1 node "$HERE/native/comp_harness.mjs" "$HERE/work/ml/comp_full.cjs" fuzz_scen.txt $F > fz_w$F.txt 2> fz_w$F.err
    else
      FA_IAT="$HERE/work/filter/iat_slots.txt" FA_POKES="$HERE/work/filter/pokes.txt" FA_DBG=1 "$HERE/work/filter/native_filter" "$CORE" fuzz_scen.txt $F > fz_n$F.txt 2> fz_n$F.err
      FA_DBG=1 node "$HERE/native/filter_harness.mjs" "$HERE/work/filter/filter.cjs" fuzz_scen.txt $F > fz_w$F.txt 2> fz_w$F.err
    fi
    m=$(paste -d'\n' fz_n$F.txt fz_w$F.txt | awk 'NR%2==1{a=$0;next}{ if(a!=$0)c++ }END{print c+0}')
    e=$(grep -c ERR fz_n$F.txt); ew=$(grep -c ERR fz_w$F.txt)
    g=$(grep -c GUARD fz_n$F.txt)
    st=OK; [ "$m" != 0 ] && { st=FAIL; fail=1; }
    echo "fuzz $TGT fma=$F: $N scenarios, mismatch $m, ERR native/wasm $e/$ew, GUARD $g -> $st"
  done
done
exit $fail
