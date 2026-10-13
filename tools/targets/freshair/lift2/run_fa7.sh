#!/usr/bin/env bash
# run_fa7.sh — FA-7 (#452): Fresh Air macro 子 param ID (0x157/0x158/0x15a) の Filter 内部パラメタ同定。
#   1) probe_ids   : Filter model ctor (0x180b4c040) を実機機械語で実行し ID descriptor 表 (417 件) を dump
#   2) probe_setid : 実 setter 0x1803debc0(M,id,v) を 3 値で呼び、M の変化バイトの位置 (= どの descriptor に書くか) と出力変化を実測。
#                    測定ごとに ctor を新規実行 (memcpy 複製は元モデルを書き換えるため不可 = alias_check 行)。
#                    陽性対照: setter 経路 (S2/S3 = 周波数/Q, PC 行) と POKE 直書き (P 行)
#   3) fa7_static_reads.py : Filter process closure (114 関数) が読む M の param 領域 disp を descriptor 表と突合
#   4) 判定 (全て fail-closed。不合格は exit 1) + ネガティブコントロール
# 前提: capstone / pefile (python)。無ければ exit 2。 build_filter.sh / build_ctrl.sh 済み (無ければ自動実行)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
[ -f "$CORE" ] || { echo "ERROR: $CORE が無い"; exit 2; }
python3 -c "import capstone, pefile" 2>/dev/null || { echo "ERROR: python capstone/pefile が必要 (uv pip install capstone pefile)"; exit 2; }
mkdir -p "$HERE/work/tmp"
[ -f "$HERE/work/filter/filter_rep.json" ] || bash "$HERE/build_filter.sh" >/dev/null || exit 2
[ -f "$HERE/work/ctrl/iat_slots.txt" ] || bash "$HERE/build_ctrl.sh" >/dev/null || exit 2
W="$HERE/work/ctrl"; cd "$W"; source "$HERE/env.sh"
clang -O1 -w -o probe_ids "$HERE/native/probe_ids.c" || exit 2
clang -O1 -w -o probe_setid "$HERE/native/probe_setid.c" || exit 2
fail=0; ck() { if [ "$2" = ok ]; then echo "  PASS $1"; else echo "  FAIL $1"; fail=1; fi; }

echo "== 1. descriptor 表"; ./probe_ids "$CORE" > ids.txt || { echo "probe_ids 失敗"; exit 1; }
FA_OBJ=1 ./probe_ids "$CORE" | grep '^OBJ' > obj.txt
head -1 ids.txt
echo "== 2. 実 setter 実測 (M 変化位置 / Filter process 出力)"
./probe_setid "$CORE" 1 2 3 4 156 157 158 159 15a 15b P9e0c=1000 P9e54=2.0 P4394=0.5 S2=200 S2=1000 S2=8000 S3=0.25 S3=0.5 S3=0.9 > setid.txt 2>&1; cut -c1-150 setid.txt
echo "== 3. closure 静的読出し"; python3 "$HERE/fa7_static_reads.py" "$CORE" "$HERE/work/filter/filter_rep.json" ids.txt | tee static.txt | head -12

judge_inert() { # setid 形式の観測 (ID 0x156..0x15b の [v=.. setErr=S .. outChanged=C perr=P]) が 18 件すべて S=0 C=0 P=0
python3 - "$1" <<'EOF'
import re, sys
TGT = (0x156, 0x157, 0x158, 0x159, 0x15a, 0x15b)
trip = re.compile(r'\[v=\S+ setErr=(\d) diffB=\d+(?: off=[0-9a-f,]+)? outChanged=(\d) perr=(\d)\]')
n = raw = bad = 0
for l in open(sys.argv[1]):
    m = re.match(r'ID 0x([0-9a-f]+):', l)
    if not m or int(m.group(1), 16) not in TGT: continue
    raw += l.count('[v=')
    for s, c, p in trip.findall(l):
        n += 1
        if (s, c, p) != ('0', '0', '0'): bad += 1
sys.exit(0 if n == 18 and raw == 18 and bad == 0 else 1)
EOF
}
judge_pc() { # setter 陽性対照 (PC 行 6 件) が全て setErr=0 perr=0 outChanged=1
python3 - "$1" <<'EOF'
import re, sys
pat = re.compile(r'PC ID 0x[23] v=\S+: setErr=(\d) diffB=\d+ outChanged=(\d) perr=(\d)$')
n = ok = 0
for l in open(sys.argv[1]):
    if not l.startswith('PC '): continue
    n += 1
    m = pat.match(l.rstrip())
    if m and m.groups() == ('0', '1', '0'): ok += 1
sys.exit(0 if n == 6 and ok == 6 else 1)
EOF
}
echo "== 4. 判定"
python3 - "$@" <<'EOF' && ck "setter 0x1803debc0 が ID 0x156..0x15b で書く M バイトは全て自 descriptor [desc_off, desc_off+0x48) 内 (6 ID × 3 値)" ok || ck "setter 書込範囲" ng
import re, sys
desc = {}
for l in open('ids.txt'):
    m = re.match(r'(\d+) desc_id=\d+ desc_off=0x([0-9a-f]+)', l)
    if m: desc[int(m.group(1))] = int(m.group(2), 16)
n = 0
for l in open('setid.txt'):
    m = re.match(r'ID 0x([0-9a-f]+):', l)
    if not m or int(m.group(1), 16) not in (0x156, 0x157, 0x158, 0x159, 0x15a, 0x15b): continue
    i = int(m.group(1), 16); lo = desc[i]
    for mm in re.finditer(r'off=([0-9a-f,]+)', l):
        for o in mm.group(1).rstrip(',').split(','):
            n += 1
            if not (lo <= int(o, 16) < lo + 0x48): print('OUT-OF-DESC', hex(i), o); sys.exit(1)
sys.exit(0 if n >= 6 * 3 else 1)    # 観測 0 件の空 PASS を拒否
EOF
judge_inert setid.txt && ck "ID 0x156..0x15b の setter 後 Filter 出力は 3 値とも不変 (18/18 で setErr=0・perr=0・outChanged=0)" ok || ck "出力不変" ng
judge_pc setid.txt && ck "陽性対照 (setter 経路): 周波数 ID 0x2 / Q ID 0x3 を setter で書くと出力が変わる (PC 6/6 で setErr=0・perr=0・outChanged=1)" ok || ck "陽性対照 setter" ng
python3 - <<'EOF' && ck "陽性対照 (POKE 直書き): M+0x9e0c / M+0x9e54 の直書きで出力が変わる (outChanged=1 ×2)" ok || ck "陽性対照 POKE" ng
import re, sys
s = open('setid.txt').read()
ok = all(re.search(r'POKE M\+0x%s=[0-9.]+: diffB=\d+ outChanged=1' % o, s) for o in ('9e0c', '9e54'))
sys.exit(0 if ok else 1)
EOF
python3 - <<'EOF' && ck "陽性対照 (FA-8 追加): setter 経由でも ID 2 (周波数) / ID 3 (Q) は 3 値とも出力が変わる (outChanged=1 が 6/6)。FA-7 の probe は setter が M0 に書き process が複製 T で動く測定バグで 0/6 だった" ok || ck "setter 経由の陽性対照" ng
import re, sys
c = t = 0
for l in open('setid.txt'):
    m = re.match(r'ID 0x([0-9a-f]+):', l)
    if m and int(m.group(1), 16) in (2, 3):
        t += l.count('outChanged='); c += l.count('outChanged=1')
sys.exit(0 if t == 6 and c == 6 else 1)
EOF
python3 - <<'EOF' && ck "ベースライン決定論 (同一入力 2 回で出力ハッシュ一致)" ok || ck "決定論" ng
import re, sys
h = open('setid.txt').readline()
a = re.search(r'base_out_hash=(\w+) base_rerun_hash=(\w+) deterministic=(\d)', h)
sys.exit(0 if a and a.group(1) == a.group(2) and a.group(3) == '1' else 1)
EOF
python3 - <<'EOF' && ck "closure 静的読出し = ID {1,2,3,4,416} のみ (期待集合と完全一致)" ok || ck "静的読出し集合" ng
import re, sys
ids = set(int(x) for l in open('static.txt') for x in re.findall(r'^  ID (\d+) ', l))
sys.exit(0 if ids == {1, 2, 3, 4, 416} else 1)
EOF

echo "== 5. ネガティブコントロール (期待集合を壊す / 出力を偽装 → FAIL すること)"
nc=0
python3 - <<'EOF' && { echo "  FAIL NC1: 期待集合 {1,2,3,4,343} が PASS してしまった"; nc=1; } || echo "  PASS NC1: 期待集合に 343 (0x157) を混ぜると不一致で FAIL"
import re, sys
ids = set(int(x) for l in open('static.txt') for x in re.findall(r'^  ID (\d+) ', l))
sys.exit(0 if ids == {1, 2, 3, 4, 343} else 1)
EOF
sed 's/outChanged=0/outChanged=1/g' setid.txt > setid_bad.txt
judge_inert setid_bad.txt && { echo "  FAIL NC2: outChanged=1 偽装が PASS"; nc=1; } || echo "  PASS NC2: setid の outChanged を 1 に改竄すると 出力不変判定が FAIL (18 件中 0 件一致)"
grep -v '^ID 0x15[6-9ab]' setid.txt > setid_empty.txt
python3 - <<'EOF' && { echo "  FAIL NC3: 観測 0 件が PASS (空 PASS)"; nc=1; } || echo "  PASS NC3: 観測行を除去すると 空 PASS せず FAIL"
import re, sys
n = 0
for l in open('setid_empty.txt'):
    m = re.match(r'ID 0x([0-9a-f]+):', l)
    if m and int(m.group(1), 16) in (0x156, 0x157, 0x158, 0x159, 0x15a, 0x15b): n += l.count('outChanged=')
sys.exit(0 if n == 18 else 1)
EOF
sed '/^PC /s/outChanged=1/outChanged=0/' setid.txt > setid_pc0.txt
judge_pc setid_pc0.txt && { echo "  FAIL NC4: setter 陽性対照の outChanged を 0 に改竄しても PASS"; nc=1; } || echo "  PASS NC4: PC 行の outChanged を 0 に改竄すると 陽性対照 (setter) が FAIL"
sed '/^ID 0x15[6-9ab]/s/setErr=0/setErr=1/g' setid.txt > setid_err.txt
judge_inert setid_err.txt && { echo "  FAIL NC5: ID 0x156..0x15b の setErr を 1 に改竄しても 判定 2 が PASS"; nc=1; } || echo "  PASS NC5: ID 0x156..0x15b の setErr を 1 に改竄すると 判定 2 が FAIL (setErr・perr も fail-closed)"
[ $nc -eq 0 ] || fail=1
echo
if [ $fail -eq 0 ]; then echo "RESULT: run_fa7 ALL PASS"; else echo "RESULT: run_fa7 FAILED"; fi
exit $fail
