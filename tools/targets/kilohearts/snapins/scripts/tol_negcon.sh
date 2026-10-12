#!/usr/bin/env bash
# tol_negcon.sh — CAB-273 (tol gate 撤去) のネガティブコントロール一式 (規則 41)。
#   1) negcon_1bit.py : 旧 snapins.json の tol が載っていた region の 1 byte に 1 bit 改変を入れ
#        ・未改変 → compare.mjs exit 0 (PASS)
#        ・改変後 (strict) → exit != 0 (FAIL 検出)
#        ・改変後 + 撤去前の --tol → exit 0 (gate が吸収していた = 撤去で塞がった穴、対照)
#   2) negcon_table.py : approx>0 の legacy snapshot を make_table.py に食わせると
#      判定列が bit-exact と誤表示されないこと (判定が実測由来であること)
#
# usage: bash scripts/tol_negcon.sh
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH=/opt/emsdk/node/24.19.0_64bit/bin:$PATH
fail=0
for n in resonator stereo delay; do
  echo "== negcon_1bit $n"
  python3 scripts/negcon_1bit.py $n || fail=1
done
echo "== negcon_table"
python3 scripts/negcon_table.py || fail=1
echo "FAIL=$fail"
exit $fail
