#!/usr/bin/env bash
# reverb_delay_e2e.sh の各 gate が「壊れた入力」で FAIL (非 0) することを確認するネガティブコントロール。
#   bash tools/plugins/reverb_delay/reverb_delay_nega.sh      (前提: reverb_delay_e2e.sh を 1 回実行済み = work/batch, work/closure, work/reverb_delay)
# 各行: 対照 (無改変) の終了コードと、壊した入力の終了コード。 期待 = 対照 0 / 壊した入力 非 0。 1 件でも期待外れなら最後に exit 1。
#   J1-J9  judge.py: 合成 CSV (emcc_c_rc / lift_rc / f80 / declares_unimpl / defines 不一致 / 行欠落 / 非数値 / 最後の行が不良 / ヘッダ違い)
#   E1     reverb_delay_e2e.sh --skip-lift 自体: status.csv に不合格行を注入して実走 → 終了コード非 0 かつ OK 行が出ない (#506 reviewer 指摘の再発防止)
#   M1-M3  matrix_check.py: facts の closure_funcs +1 / status の emcc_c_rc を matrix と食い違わせる / matrix に無い plugin
#   I1-I3  ids_crosscheck.py: taint の ID 件数 +1 / hs_ids.json に無い ID を注入 / facts が指す closure json が無い
#   X1-X3  xcheck_icall.py: audit の site を 1 つ捨てる / audit に存在しない site を足す / expected の VA を 1 つ消す
#   L1-L2  lift 鎖: final.ll の ret を除去すると emcc -c が非 0 / 閉包 ranges の末尾 1 つを落とした従来鎖 (PLUG_ICALL=0) lift の defines を judge に渡すと FAIL
#   P1     ipp_use.py: 既知の IPP 使用関数を閉包に加えた closure json で users_in_closure が 0 → 1 以上になる (検出器の positive control)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
export PLUG_ICALL=1   # 既定鎖 (J/E/M/I/X/P は既定鎖の成果物を使う)。 L2 だけ PLUG_ICALL=0 を明示
R=reverb_delay
O=work/reverb_delay
N=$O/nega; rm -rf "$N"; mkdir -p "$N/tmp"
BLOCKS=(18992 18996 18998 18999 19002 19067 19069 19146 19164)
FAILS=0
chk() {  # name ctrl_rc bad_rc [extra]
  local ok=no
  [ "$2" = 0 ] && [ "$3" != 0 ] && ok=yes
  [ "$ok" = yes ] || FAILS=$((FAILS + 1))
  printf '%-4s control rc=%-3s  broken rc=%-3s  %s %s\n' "$1" "$2" "$3" "$([ $ok = yes ] && echo DETECTED || echo NOT-DETECTED)" "${4:-}"
}
rc() { "$@" > /dev/null 2>&1; echo $?; }

# ---- J: judge.py (合成 CSV; lift 不要で数秒) ----
S=$O/status9.csv
c0=$(rc python3 $R/judge.py $S "${BLOCKS[@]}" --closure-dir work/closure); jc=$c0
mut() {  # tag python-expr-on-rows(list of list, header stripped)
  python3 - "$S" "$N/$1.csv" "$2" <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1])))
hdr, body = rows[0], rows[1:]
exec(sys.argv[3])
csv.writer(open(sys.argv[2], 'w')).writerows([hdr] + body)
PY
}
# 列: 0 block,1 name,2 closure_funcs,3 closure_bytes,4 lift_rc,5 defines,6 declares_unimpl,7 f80_funcs,8 emcc_c_rc,9 seconds
mut j1 "body[1][8]='1'";            chk J1 $c0 $(rc python3 $R/judge.py $N/j1.csv "${BLOCKS[@]}") "(Delay emcc_c_rc=1)"
mut j2 "body[3][4]='1'";            chk J2 $c0 $(rc python3 $R/judge.py $N/j2.csv "${BLOCKS[@]}") "(Delay 3 lift_rc=1)"
mut j3 "body[0][7]='3'";            chk J3 $c0 $(rc python3 $R/judge.py $N/j3.csv "${BLOCKS[@]}") "(Convolver f80_funcs=3)"
mut j4 "body[7][6]='5'";            chk J4 $c0 $(rc python3 $R/judge.py $N/j4.csv "${BLOCKS[@]}") "(LuxeVerb declares_unimpl=5)"
mut j5 "body[2][5]=str(int(body[2][5])-1)"; chk J5 $c0 $(rc python3 $R/judge.py $N/j5.csv "${BLOCKS[@]}") "(Delay 2 defines = closure_funcs-1)"
mut j6 "del body[5]";               chk J6 $c0 $(rc python3 $R/judge.py $N/j6.csv "${BLOCKS[@]}") "(Reeverb の行を削除)"
mut j7 "body[4][8]='x'";            chk J7 $c0 $(rc python3 $R/judge.py $N/j7.csv "${BLOCKS[@]}") "(Delay Bank emcc_c_rc='x')"
mut j8 "bad=list(body[6]); bad[8]='1'; body.append(bad)"; chk J8 $c0 $(rc python3 $R/judge.py $N/j8.csv "${BLOCKS[@]}") "(Reeverb 2 に不良の追記行 = 最後の行を採用)"
mut j9 "hdr[4]='lift_rcX'";         chk J9 $c0 $(rc python3 $R/judge.py $N/j9.csv "${BLOCKS[@]}") "(ヘッダ違い)"

# ---- E1: e2e 自体の終了コード (本物の work/batch/status.csv を一時的に差し替える。 trap で必ず戻す) ----
cp work/batch/status.csv "$N/status.csv.orig"
trap 'cp "$N/status.csv.orig" work/batch/status.csv' EXIT
python3 - work/batch/status.csv <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1])))
for r in rows[1:]:
    if r[0] == '18996':
        r[8] = '1'
csv.writer(open(sys.argv[1], 'w')).writerows(rows)
PY
bash $R/reverb_delay_e2e.sh --skip-lift > "$N/e1.log" 2>&1; e1=$?
cp "$N/status.csv.orig" work/batch/status.csv
bash $R/reverb_delay_e2e.sh --skip-lift > "$N/e1ctl.log" 2>&1; e1c=$?
okline=$(grep -c '^\[reverb_delay_e2e\] OK' "$N/e1.log")
chk E1 $e1c $e1 "(e2e 実走。 broken 側の OK 行数=$okline、期待 0。 judge 出力: $(grep -m1 'FAIL' $N/e1.log | cut -c1-80))"
[ "$okline" = 0 ] || FAILS=$((FAILS + 1))

# ---- M: matrix_check.py ----
python3 - <<'PY'
import json, csv
F = json.load(open('work/reverb_delay/facts.json'))
F['Fruity Delay']['closure_funcs'] += 1
json.dump(F, open('work/reverb_delay/nega/facts_m1.json', 'w'))
rows = list(csv.reader(open('work/reverb_delay/status9.csv')))
for r in rows[1:]:
    if r[0] == '18996':
        r[8] = '1'
csv.writer(open('work/reverb_delay/nega/status_m2.csv', 'w')).writerows(rows)
F = json.load(open('work/reverb_delay/facts.json'))
F['No Such Plugin'] = F['Fruity Delay']
json.dump(F, open('work/reverb_delay/nega/facts_m3.json', 'w'))
PY
m0=$(rc python3 $R/matrix_check.py)
chk M1 $m0 $(rc python3 $R/matrix_check.py --facts $N/facts_m1.json) "(Delay closure_funcs +1)"
chk M2 $m0 $(rc python3 $R/matrix_check.py --status $N/status_m2.csv) "(Delay emcc_c_rc=1 vs matrix batch=0)"
chk M3 $m0 $(rc python3 $R/matrix_check.py --facts $N/facts_m3.json) "(matrix に無い plugin)"

# ---- I: ids_crosscheck.py ----
python3 - <<'PY'
import json
F = json.load(open('work/reverb_delay/facts.json'))
F['LuxeVerb']['host']['ids']['50'] += 1
json.dump(F, open('work/reverb_delay/nega/facts_i1.json', 'w'))
F = json.load(open('work/reverb_delay/facts.json'))
F['Fruity Delay']['host']['ids']['999'] = 1
json.dump(F, open('work/reverb_delay/nega/facts_i2.json', 'w'))
F = json.load(open('work/reverb_delay/facts.json'))
F['Fruity Delay']['block'] = 99999
json.dump(F, open('work/reverb_delay/nega/facts_i3.json', 'w'))
PY
i0=$(rc python3 $R/ids_crosscheck.py)
chk I1 $i0 $(rc python3 $R/ids_crosscheck.py --facts $N/facts_i1.json) "(LuxeVerb ID 50 の taint 件数 +1)"
chk I2 $i0 $(rc python3 $R/ids_crosscheck.py --facts $N/facts_i2.json) "(hs_ids.json に無い ID 999 を注入)"
chk I3 $i0 $(rc python3 $R/ids_crosscheck.py --facts $N/facts_i3.json) "(存在しない block)"

# ---- X: xcheck_icall.py ----
ID=$O/icall
x0=$(rc python3 $R/xcheck_icall.py "${BLOCKS[@]}")
rm -rf $N/icall_x1 $N/icall_x2; cp -r $ID $N/icall_x1; cp -r $ID $N/icall_x2
python3 - <<'PY'
import json
d = 'work/reverb_delay/nega/icall_x1/18996.sites.json'
s = json.load(open(d))
i = next(k for k, x in enumerate(s) if x['mn'] == 'call' and x['kind'] != 'iat')
del s[i]
json.dump(s, open(d, 'w'))
d = 'work/reverb_delay/nega/icall_x2/18996.sites.json'
s = json.load(open(d))
extra = dict(next(x for x in s if x['mn'] == 'call' and x['kind'] != 'iat'))
extra['va'] += 1
s.append(extra)
json.dump(s, open(d, 'w'))
PY
grep -v '0x875dd7' reverb_delay/icall_linear_only.expected > $N/expected_x3
chk X1 $x0 $(rc python3 $R/xcheck_icall.py --dir $N/icall_x1 "${BLOCKS[@]}") "(Delay の audit site を 1 つ捨てる)"
chk X2 $x0 $(rc python3 $R/xcheck_icall.py --dir $N/icall_x2 "${BLOCKS[@]}") "(audit に存在しない site を足す)"
chk X3 $x0 $(rc python3 $R/xcheck_icall.py --expected $N/expected_x3 "${BLOCKS[@]}") "(expected から 0x875dd7 を消す)"

# ---- L: lift 鎖 (Fruity Delay 18996 = 最小閉包) ----
B=18996
OUT=work/batch/$B
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
emcc_rc() { ( TMPDIR="$N/tmp" emcc -c "$1" -o "$N/x.o" -w -O0 -msimd128 > "$N/emcc.log" 2>&1 ); echo $?; }
c0=$(emcc_rc $OUT/p.final.ll)
python3 - $OUT/p.final.ll $N/broken.ll <<'PY'
import sys
s = open(sys.argv[1]).read()
i = s.index('\ndefine ')
j = s.index('\n}\n', i)
body = s[i:j]
k = body.rindex('\n  ret ')
open(sys.argv[2], 'w').write(s[:i] + body[:k] + s[j:])
PY
chk L1 $c0 $(emcc_rc $N/broken.ll) "(final.ll の関数 1 つから ret を除去 → emcc -c)"
RG=work/closure/block$(printf %05d $B).ranges.txt
n_all=$(tr ',' '\n' < $RG | wc -l)
tr ',' '\n' < $RG | head -n $((n_all - 1)) | paste -sd, > $N/ranges_minus1.txt
PLUG_ICALL=0 bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin" $N/ranges_minus1.txt $N/lift p 600 > $N/lift.log 2>&1
d1=$(grep -c '^define' $N/lift/p.final.ll)
python3 - $S $N/status_l2.csv $B $d1 <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1])))
for r in rows[1:]:
    if r[0] == sys.argv[3]:
        r[5] = sys.argv[4]
csv.writer(open(sys.argv[2], 'w')).writerows(rows)
PY
echo "     (L2 ranges $n_all -> $((n_all - 1)): 再 lift の defines=$d1、元の ranges $n_all 本 / 閉包関数 $(python3 -c "import json;print(json.load(open('work/closure/block$(printf %05d $B).json'))['unique_funcs'])") )"
chk L2 $jc $(rc python3 $R/judge.py $N/status_l2.csv "${BLOCKS[@]}") "(ranges-1 の defines=$d1 を Delay の行に入れて judge)"

# ---- P: ipp_use.py positive control ----
python3 - <<'PY'
import json
j = json.load(open('work/reverb_delay/ipp_use.json'))['18992']
va = int(sorted(j['user_vas'])[0], 16)
c = json.load(open('work/closure/block18992.json'))
c['ranges'] = c['ranges'] + ['0x%x-0x%x' % (va, va + 1)]
import os
os.makedirs('work/reverb_delay/nega/closure_p1', exist_ok=True)
json.dump(c, open('work/reverb_delay/nega/closure_p1/block18992.json', 'w'))
print(hex(va))
PY
p_ctl=$(python3 $R/ipp_use.py 18992 | grep -o 'users_in_closure=[0-9]*')
p_bad=$(python3 $R/ipp_use.py --closure-dir $N/closure_p1 18992 | grep -o 'users_in_closure=[0-9]*')
pok=no; [ "$p_ctl" = "users_in_closure=0" ] && [ "$p_bad" != "users_in_closure=0" ] && pok=yes
[ $pok = yes ] || FAILS=$((FAILS + 1))
echo "P1   control $p_ctl  closure に既知 IPP 使用関数を加えた: $p_bad  $([ $pok = yes ] && echo DETECTED || echo NOT-DETECTED)"

if [ "$FAILS" = 0 ]; then echo "[reverb_delay_nega] OK: 全 NC 検出"; exit 0; fi
echo "[reverb_delay_nega] FAIL: $FAILS 件が期待外れ" >&2; exit 1
