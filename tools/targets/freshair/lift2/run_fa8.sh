#!/usr/bin/env bash
# run_fa8.sh [N=400] — FA-8 (#648): Filter model setter 0x1803debc0 の native(実機機械語) vs wasm(mlift) bit-exact + 型別 ID 感度。
#   G1 native/wasm bit-exact (N 本 × fma 0/1, 全 PASS・ERR 0・行数 N)
#   G2 ID 0x157/0x158/0x15a の setter は Filter 出力を変えない (type 0..7 の 8/8, native と wasm 両方)
#   G3 陽性対照: ID 2 / 3 の setter は全 type で出力を変える (8/8)、ID 4 は type 4..6 のみ (実測集合と完全一致)
#   NC1..NC4: 判定を壊して FAIL することを確認。不合格は exit 1、前提不足は exit 2。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
[ -f "$CORE" ] || { echo "ERROR: $CORE が無い"; exit 2; }
python3 -c "import capstone, pefile" 2>/dev/null || { echo "ERROR: python capstone/pefile が必要"; exit 2; }
N="${1:-400}"; W="$HERE/work/fa8"; mkdir -p "$HERE/work/tmp" "$W"
[ -f "$W/fset.cjs" ] || bash "$HERE/build_setter.sh" >/dev/null || { echo "build_setter 失敗"; exit 2; }
cd "$W"; source "$HERE/env.sh"
clang -O1 -w -o native_setter "$HERE/native/native_setter.c" || exit 2
fail=0; ck() { if [ "$2" = ok ]; then echo "  PASS $1"; else echo "  FAIL $1"; fail=1; fi; }
mism() { paste -d'\n' "$1" "$2" | awk 'NR%2==1{a=$0;next}{if(a!=$0)c++}END{print c+0}'; }

echo "== G1. native vs wasm bit-exact (ランダム ${N} 本 × fma0/1)"
python3 "$HERE/gen_setter_scen.py" scen.txt "$N" >/dev/null
for F in 0 1; do
  ./native_setter "$CORE" scen.txt $F > n$F.txt 2> n$F.err
  node "$HERE/native/setter_harness.mjs" ./fset.cjs scen.txt $F > w$F.txt 2> w$F.err
  echo "  fma=$F: native 行 $(wc -l < n$F.txt) / wasm 行 $(wc -l < w$F.txt), ERR $(grep -c ERR n$F.txt)/$(grep -c ERR w$F.txt), mismatch $(mism n$F.txt w$F.txt)"
done
g1() { local ok=1; for F in 0 1; do
  [ "$(wc -l < n$F.txt)" -eq "$N" ] && [ "$(wc -l < w$F.txt)" -eq "$N" ] && [ "$(grep -c ERR n$F.txt w$F.txt | awk -F: '{s+=$2}END{print s}')" -eq 0 ] && [ "$(mism n$F.txt w$F.txt)" -eq 0 ] || ok=0; done; [ $ok -eq 1 ]; }
g1 && ck "setter 後 process 出力 + DSP param dword が native/wasm 全バイト一致 ($N 本 × 2)" ok || ck "native/wasm bit-exact" ng

echo "== G2/G3. 型別 ID 感度 (type 0..7 × {baseline, 157+158+15a, ID2+ID3, ID4} 各 3 call 同一入力 seed)"
python3 - <<'EOF'
import struct
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
V = {'base': [], 'fa7': [(0x157, fb(0.7819324)), (0x158, fb(0.8366389)), (0x15a, fb(0.0))], 'id23': [(2, fb(0.5)), (3, fb(0.9))], 'id4': [(4, fb(0.9))]}
L = []
for t in range(8):
    for k, s in V.items():
        L.append(' '.join('%x' % x for x in [t * 16 + list(V).index(k), t, len(s)] + [y for a in s for y in a] + [3, 0xABCDEF]))
open('sens.txt', 'w').write('\n'.join(L) + '\n')
EOF
./native_setter "$CORE" sens.txt 0 > sn.txt 2>/dev/null; node "$HERE/native/setter_harness.mjs" ./fset.cjs sens.txt 0 > sw.txt 2>/dev/null
cat > sens.py <<'EOF'
import sys
# 引数: ファイル 期待 (fa7 不変の type 集合 / id23 変化の type 集合 / id4 変化の type 集合)。出力 = 3 集合 + 件数
def lr(line):   # L/R の hex のみ (各 call の '|L R D' の D=DSP dword は比較から除く: setter が書く値自体は変わって当然)
    out = []
    for c in line.split(' |')[1:]:
        p = c.split(' '); out.append(p[0] + p[1])
    return out
rows = [l.rstrip('\n') for l in open(sys.argv[1])]
if len(rows) != 32 or any('ERR' in r or len(lr(r)) != 3 for r in rows): print('BAD'); sys.exit(1)
inv, c23, c4 = [], [], []
for t in range(8):
    b, f7, i23, i4 = (lr(rows[t * 4 + k]) for k in range(4))
    if f7 == b: inv.append(t)
    if i23 != b: c23.append(t)
    if i4 != b: c4.append(t)
print(' '.join(','.join(map(str, x)) or '-' for x in (inv, c23, c4)))
EOF
RN=$(python3 sens.py sn.txt) || RN=BAD; RW=$(python3 sens.py sw.txt) || RW=BAD
echo "  native: 0x157/0x158/0x15a 不変 type = {${RN%% *}} / ID2+3 変化 type = {$(echo $RN | cut -d' ' -f2)} / ID4 変化 type = {${RN##* }}"
echo "  wasm  : 0x157/0x158/0x15a 不変 type = {${RW%% *}} / ID2+3 変化 type = {$(echo $RW | cut -d' ' -f2)} / ID4 変化 type = {${RW##* }}"
[ "${RN%% *}" = "0,1,2,3,4,5,6,7" ] && [ "${RW%% *}" = "0,1,2,3,4,5,6,7" ] && ck "ID 0x157+0x158+0x15a の setter は Filter 出力を変えない (type 0..7 の 8/8, native/wasm)" ok || ck "0x157.. 不変 (8/8)" ng
[ "$(echo $RN | cut -d' ' -f2)" = "0,1,2,3,4,5,6,7" ] && [ "$(echo $RW | cut -d' ' -f2)" = "0,1,2,3,4,5,6,7" ] && ck "陽性対照: ID 2+3 (周波数/Q) の setter は全 type で出力を変える (8/8, native/wasm)" ok || ck "陽性対照 ID2+3" ng
[ "${RN##* }" = "4,5,6" ] && [ "${RW##* }" = "4,5,6" ] && ck "陽性対照: ID 4 は type 4,5,6 のみ出力を変える (native/wasm)" ok || ck "陽性対照 ID4" ng
[ "$RN" = "$RW" ] && ck "感度判定は native/wasm で一致" ok || ck "感度 native/wasm 一致" ng

echo "== NC. ネガティブコントロール (判定を壊して FAIL すること)"
nc=0
# NC1: wasm 出力の 1 文字を改竄 → mismatch 1
sed '1s/^\(S0 |.\{20\}\)./\1X/' w0.txt > w_bad.txt
[ "$(mism n0.txt w_bad.txt)" -eq 1 ] && echo "  PASS NC1: wasm 出力 1 文字改竄 → mismatch=1 (bit-exact 判定が FAIL する)" || { echo "  FAIL NC1"; nc=1; }
# NC2: 行を 1 本欠落 → 行数判定
head -n $((N-1)) w0.txt > w_short.txt
[ "$(wc -l < w_short.txt)" -ne "$N" ] && echo "  PASS NC2: wasm 出力を $((N-1)) 行に欠落 → 行数 $(wc -l < w_short.txt) ≠ $N (空/欠落 PASS を拒否)" || { echo "  FAIL NC2"; nc=1; }
# NC3: 実判定 sens.py に、各 type の fa7 行 (k=1) を id23 行 (k=2) で差替えた sn を食わせる → 「不変 type」集合が空になるはず
python3 - <<'EOF2'
rows = [l for l in open('sn.txt').read().split('\n') if l]
for t in range(8): rows[t * 4 + 1] = rows[t * 4 + 2]
open('sn_bad3.txt', 'w').write('\n'.join(rows) + '\n')
EOF2
R3=$(python3 sens.py sn_bad3.txt) || R3=BAD
[ "${R3%% *}" != "0,1,2,3,4,5,6,7" ] && echo "  PASS NC3: fa7 行を ID2+3 行に差替えると 実判定の不変 type 集合が {${R3%% *}} になり 8/8 判定が FAIL" || { echo "  FAIL NC3: 差替えても 8/8 のまま"; nc=1; }
# NC4: 実判定に、id23 行 (k=2) を base 行 (k=0) で差替えた sn を食わせる → 陽性対照 (ID2+3 が全 type で変化) が崩れるはず
python3 - <<'EOF2'
rows = [l for l in open('sn.txt').read().split('\n') if l]
for t in range(8): rows[t * 4 + 2] = rows[t * 4]
open('sn_bad4.txt', 'w').write('\n'.join(rows) + '\n')
EOF2
R4=$(python3 sens.py sn_bad4.txt) || R4=BAD
[ "$(echo $R4 | cut -d' ' -f2)" != "0,1,2,3,4,5,6,7" ] && echo "  PASS NC4: id23 行を base 行に差替えると 陽性対照の変化 type 集合が {$(echo $R4 | cut -d' ' -f2)} になり 8/8 判定が FAIL (測定系が無変化を検出する)" || { echo "  FAIL NC4"; nc=1; }
[ $nc -eq 0 ] || fail=1
echo
if [ $fail -eq 0 ]; then echo "RESULT: run_fa8 ALL PASS"; else echo "RESULT: run_fa8 FAILED"; fi
exit $fail
