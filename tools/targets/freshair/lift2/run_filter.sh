#!/usr/bin/env bash
# run_filter.sh [N=200] [seed] — Filter process: native(実機機械語) vs wasm(mlift) bit-exact 比較 (fma 0/1)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
W="$HERE/work/filter"; cd "$W"; source "$HERE/env.sh"
N="${1:-200}"; SEED="${2:-0xF117E4}"
clang -O1 -w -o native_filter "$HERE/native/native_filter.c"
python3 "$HERE/gen_filter_scen.py" filter_scen.txt "$N" "$SEED" >/dev/null
tot=0; bad=0
for F in 0 1; do
  FA_DBG=1 ./native_filter "$CORE" filter_scen.txt $F > f_n$F.txt 2> f_n$F.err
  FA_DBG=1 node "$HERE/native/filter_harness.mjs" ./filter.cjs filter_scen.txt $F > f_w$F.txt 2> f_w$F.err
  m=$(paste -d'\n' f_n$F.txt f_w$F.txt | awk 'NR%2==1{a=$0;next}{ if(a!=$0)c++ }END{print c+0}')
  ncalls=$(grep -o '|' f_n$F.txt | wc -l)
  echo "fma=$F: scenarios $N, calls $ncalls, mismatch $m, ERR native/wasm $(grep -c ERR f_n$F.txt)/$(grep -c ERR f_w$F.txt)"
  tot=$((tot+N)); bad=$((bad+m))
done
if [ "$bad" = 0 ]; then echo "RESULT: BIT-EXACT $tot/$tot scenarios (fma0+fma1)"; else echo "RESULT: MISMATCH $bad/$tot"; exit 1; fi
