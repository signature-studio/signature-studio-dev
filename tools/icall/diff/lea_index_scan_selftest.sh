#!/usr/bin/env bash
# lea_index_scan_selftest.sh — lea_index_scan.py の負の対照 (ICALL-86 / #3136)。合成の objdump 入力で検出と非検出を確かめる。
#   正  : lea 基底 0x1813068c0 + 添字 rdx*8 + disp 0x10 → 5 件の先頭 0x1813068d0 に添字 0 で届く (判定「届く」・区分「定数一致」)。
#   負 1: disp を 0x11 に壊す → 整除できず候補 0 件。
#   負 2: 添字を mov edx,0x1 に変える → 判定「届かない」・区分「定数不一致」。
#   負 3 (B1): 分岐先を 0x 無しの形式 (je 180001011 <f+0x11>) で書く。je 経路は rdx=0 で届くので、011 の候補は「届かない」にならない。
#   負 4 (B2): 基底 rdx の定義が lea だけでも、je 経路は入口由来なので、「届かない」にならない (届き得る)。
#   用法: bash tools/icall/diff/lea_index_scan_selftest.sh   (rc=0 で全件 PASS)
#   作業は $RUNNER_TEMP (無ければ $TMPDIR・/tmp) に置く。tools/**/work/ は使わない。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
W="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/lea_selftest.$$"
mkdir -p "$W"
trap 'rm -rf "$W"' EXIT
printf '  180001000:\t48 8d 05 00 00 00 00 \tlea    rax,[rip+0x0]        # 0x1813068c0\n' > "$W/pos.txt"
printf '  180001007:\tba 00 00 00 00 \tmov    edx,0x0\n' >> "$W/pos.txt"
printf '  18000100c:\t48 8b 4c d0 10 \tmov    rcx,QWORD PTR [rax+rdx*8+0x10]\n' >> "$W/pos.txt"
printf '  180001011:\tc3 \tret\n' >> "$W/pos.txt"
sed 's/rdx\*8+0x10\]/rdx*8+0x11]/' "$W/pos.txt" > "$W/neg_disp.txt"
sed 's/mov    edx,0x0/mov    edx,0x1/' "$W/pos.txt" > "$W/neg_const.txt"
printf '  180001000:\t48 8d 05 00 00 00 00 \tlea    rax,[rip+0x0]        # 0x1813068c0\n' > "$W/sym_jt.txt"
printf '  180001007:\t31 d2 \txor    edx,edx\n' >> "$W/sym_jt.txt"
printf '  180001009:\t74 06 \tje     180001011 <f+0x11>\n' >> "$W/sym_jt.txt"
printf '  18000100b:\tba 09 00 00 00 \tmov    edx,0x9\n' >> "$W/sym_jt.txt"
printf '  180001010:\t90 \tnop\n' >> "$W/sym_jt.txt"
printf '  180001011:\t48 8b 4c d0 10 \tmov    rcx,QWORD PTR [rax+rdx*8+0x10]\n' >> "$W/sym_jt.txt"
printf '  180001016:\tc3 \tret\n' >> "$W/sym_jt.txt"
printf '  180001000:\t85 c9 \ttest   ecx,ecx\n' > "$W/flow.txt"
printf '  180001002:\t74 07 \tje     18000100b <f+0xb>\n' >> "$W/flow.txt"
printf '  180001004:\t48 8d 15 00 00 00 00 \tlea    rdx,[rip+0x0]        # 0x181306000\n' >> "$W/flow.txt"
printf '  18000100b:\t0f b6 37 \tmovzx  esi,BYTE PTR [rdi]\n' >> "$W/flow.txt"
printf '  18000100e:\t48 8b 4c f2 10 \tmov    rcx,QWORD PTR [rdx+rsi*8+0x10]\n' >> "$W/flow.txt"
printf '  180001013:\tc3 \tret\n' >> "$W/flow.txt"
rc=0
check() {
  local name="$1" file="$2" want="$3" n
  out="$(python3 "$HERE/lea_index_scan.py" "$file" - 2>&1)"
  n="$(grep -c $'\tX=' <<< "$out" || true)"
  if grep -qF -- "$want" <<< "$out"; then echo "PASS $name (候補行 $n・期待 '$want')"; else echo "FAIL $name (候補行 $n・期待 '$want' が無い)"; rc=1; fi
}
verdict_of() {
  python3 "$HERE/lea_index_scan.py" "$1" - 2>&1 | awk -F'\t' -v v="$2" '$1==v {print $10}' | sort -u | paste -sd, -
}
check_v() {
  local name="$1" file="$2" va="$3" want="$4" got
  got="$(verdict_of "$file" "$va")"
  if [ "$got" = "$want" ]; then echo "PASS $name (VA $va の判定 '$got')"; else echo "FAIL $name (VA $va の判定 '$got'・期待 '$want')"; rc=1; fi
}
check "正 (届く)" "$W/pos.txt" $'\t届く\t定数一致\t'
check "負1 disp 破壊 (候補 0)" "$W/neg_disp.txt" "・候補 0 件"
check "負2 定数変更 (届かない)" "$W/neg_const.txt" $'\t届かない\t定数不一致\t'
check_v "負3 je <sym> の分岐先 (境界・届かない にしない)" "$W/sym_jt.txt" 180001011 "届き得る"
check_v "負4 流れ非依存の基底 (届かない にしない)" "$W/flow.txt" 18000100e "届き得る"

exit $rc
