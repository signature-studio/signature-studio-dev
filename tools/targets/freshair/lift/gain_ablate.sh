#!/usr/bin/env bash
# 対照実験: 修復 pass を 1 つずつ無効化し, native との不一致シナリオ数を実測 (gain_e2e.sh 実行後に使う)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"; W="$FA/work/lift_gain"; cd "$W"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
for skip in P1 F7 F2; do
  FA_SKIP=$skip python3 "$HERE/fa_fix_gain.py" gain_lift.ll abl_$skip.ll >/dev/null
  if emcc -w -O1 -ffp-contract=off -frounding-math abl_$skip.ll "$HERE/fa_simd.c" "$HERE/fa_stub.c" "$HERE/abl_extra.c" -sERROR_ON_UNDEFINED_SYMBOLS=1 -sMODULARIZE=1 -sENVIRONMENT=node -sALLOW_MEMORY_GROWTH=1 \
      -sEXPORTED_FUNCTIONS=_malloc,_free,_function_180afe090 -sEXPORTED_RUNTIME_METHODS=HEAPU8 --no-entry -o abl_$skip.js 2>abl_$skip.err; then
    mv abl_$skip.js abl_$skip.cjs
    node "$HERE/gain_harness.mjs" ./abl_$skip.cjs scen.txt > out_abl_$skip.txt 2>abl_$skip.err2 || true
    tot=$(wc -l < out_native.txt); got=$(wc -l < out_abl_$skip.txt)
    bad=$(awk 'NR==FNR{a[FNR]=$0;next}{if(a[FNR]!=$0)c++}END{print c+0}' out_native.txt out_abl_$skip.txt)
    echo "ablate $skip: mismatch $bad / $got executed scenarios; executed $got/$tot$([ "$got" -lt "$tot" ] && echo " (wasm trapped: $(grep -m1 -o 'RuntimeError[^\n]*' abl_$skip.err2 | head -1))")"
  else echo "ablate $skip: emcc FAIL: $(head -c 200 abl_$skip.err)"; fi
done
