#!/usr/bin/env bash
# lea_index_scan_selftest.sh — lea_index_scan.py の負の対照 (ICALL-86 / #3136)。合成の objdump 入力で検出と非検出を確かめる。
#   正  : lea 基底 0x1813068c0 + 添字 rdx*8 + disp 0x10 → 5 件の先頭 0x1813068d0 に添字 0 で届く (判定「届く」・区分「定数一致」)。
#   負 1: disp を 0x11 に壊す → 整除できず候補 0 件。
#   負 2: 添字を mov edx,0x1 に変える → 判定「届かない」・区分「定数不一致」。
#   用法: bash tools/icall/diff/lea_index_scan_selftest.sh   (rc=0 で全件 PASS)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T="$HERE/../.."
W="$T/icall/work/lea_selftest"
mkdir -p "$W"
printf '  180001000:\t48 8d 05 00 00 00 00 \tlea    rax,[rip+0x0]        # 0x1813068c0\n' > "$W/pos.txt"
printf '  180001007:\tba 00 00 00 00 \tmov    edx,0x0\n' >> "$W/pos.txt"
printf '  18000100c:\t48 8b 4c d0 10 \tmov    rcx,QWORD PTR [rax+rdx*8+0x10]\n' >> "$W/pos.txt"
printf '  180001011:\tc3 \tret\n' >> "$W/pos.txt"
sed 's/rdx\*8+0x10\]/rdx*8+0x11]/' "$W/pos.txt" > "$W/neg_disp.txt"
sed 's/mov    edx,0x0/mov    edx,0x1/' "$W/pos.txt" > "$W/neg_const.txt"
rc=0
check() {
  local name="$1" file="$2" want="$3" n
  out="$(python3 "$HERE/lea_index_scan.py" "$file" - 2>&1)"
  n="$(grep -c $'\tX=' <<< "$out" || true)"
  if grep -qF -- "$want" <<< "$out"; then echo "PASS $name (候補行 $n・期待 '$want')"; else echo "FAIL $name (候補行 $n・期待 '$want' が無い)"; rc=1; fi
}
check "正 (届く)" "$W/pos.txt" $'\t届く\t定数一致\t'
check "負1 disp 破壊 (候補 0)" "$W/neg_disp.txt" "・候補 0 件"
check "負2 定数変更 (届かない)" "$W/neg_const.txt" $'\t届かない\t定数不一致\t'

exit $rc
