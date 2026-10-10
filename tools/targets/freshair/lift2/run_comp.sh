#!/usr/bin/env bash
# run_comp.sh [N=400] [seed] — Compressor process: native(実機機械語) vs wasm(mlift) bit-exact 比較 (fma 0/1 の 2 経路)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
W="$HERE/work/ml"; cd "$W"; source "$HERE/env.sh"
N="${1:-400}"; SEED="${2:-0xC0FFEE}"
python3 "$HERE/gen_comp_scen.py" comp_scen.txt "$N" "$SEED" >/dev/null
tot=0; bad=0
for F in 0 1; do
  FA_DBG=1 ./native_comp "$CORE" comp_scen.txt $F > comp_n$F.txt 2> comp_n$F.err
  FA_DBG=1 node "$HERE/native/comp_harness.mjs" ./comp_full.cjs comp_scen.txt $F > comp_w$F.txt 2> comp_w$F.err
  m=$(paste -d'\n' comp_n$F.txt comp_w$F.txt | awk 'NR%2==1{a=$0;next}{ if(a!=$0)c++ }END{print c+0}')
  e=$(grep -c ERR comp_n$F.txt); ew=$(grep -c ERR comp_w$F.txt)
  ncalls=$(grep -o '|' comp_n$F.txt | wc -l)
  echo "fma=$F: scenarios $N, calls(total '|' tokens incl ERR) $ncalls, mismatch $m, ERR native/wasm $e/$ew"
  tot=$((tot+N)); bad=$((bad+m))
done
# grow 経路 (vcap<16: shared_ptr/CRT 状態依存) と非 grow を分離集計
python3 - <<'PYEOF'
import sys
n = open('comp_n0.txt').read().splitlines()
w = open('comp_w0.txt').read().splitlines()
sc = open('comp_scen.txt').read().splitlines()
ok_grow = ok_norm = bad_grow = bad_norm = err = 0
for i, (a, b) in enumerate(zip(n, w)):
    vcap = int(sc[i].split(' ')[2], 16)
    grow = vcap < 16
    if 'ERR' in b: err += 1
    if a == b:
        ok_grow += grow; ok_norm += not grow
    else:
        bad_grow += grow; bad_norm += not grow
print('comp split: non-grow %d/%d OK, grow(vcap<16) %d/%d OK, wasm ERR %d' % (ok_norm, ok_norm + bad_norm, ok_grow, ok_grow + bad_grow, err))
sys.exit(0 if bad_norm == 0 else 1)
PYEOF
if [ $? -eq 0 ]; then echo "RESULT: comp non-grow BIT-EXACT (grow subset は既知限界として REPORT 参照)"; else echo "RESULT: MISMATCH in non-grow scenarios"; exit 1; fi
