#!/usr/bin/env bash
# ctlvfx_e2e.sh の各 gate の識別力を確認するネガティブコントロール (NC)。 事前: ctlvfx_e2e.sh を実行済み (work/ctlvfx/{status.csv,facts.json} と work/batch/19096 がある)。
#   NC-J*: judge.py に、実測の status.csv を 1 箇所だけ壊したコピーを渡す → 非 0 で終わること (対照: 無改変は 0)
#   NC-E : ctlvfx_e2e.sh --judge-only に不合格 CSV → exit 非 0 かつ `[ctlvfx_e2e] OK` を出さないこと (対照: 合格 CSV は exit 0 + OK)
#   NC-M : matrix_check.py に壊した facts / PLUGIN_MATRIX → exit 1
#   NC-I : ids_crosscheck.py に taint 側 ID +1 / plugin 欠落の facts → exit 1
#   NC-D : closure_defs.py に define 脱落 / 閉包外混入 / final.ll 無しの batch → exit 1
#   NC-L1/L2: lift 本体 (最小の閉包 Fruity dB meter 19096): final.ll を壊すと emcc -c が FAIL / ranges を 1 つ落とすとその関数が消える
# exit 0 = 全 NC が期待どおり (識別できた)。 1 つでも期待を外せば exit 1。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
N=work/ctlvfx/nega; rm -rf "$N"; mkdir -p "$N/tmp"
S0=work/ctlvfx/status.csv; F=work/ctlvfx/facts.json; S=$N/base.csv
M="python3 ctlvfx/nega_mut.py"
$M csv-pass $S0 $S   # 基準: 実測の行を合格値にそろえたもの (実測に不合格があっても NC の対照にできる)
NG=0
# expect <名前> <期待 rc: 0 | nz | 数値> <実 rc>
expect() {
  local ok=0
  case "$2" in 0) [ "$3" = 0 ] && ok=1 ;; nz) [ "$3" != 0 ] && ok=1 ;; *) [ "$3" = "$2" ] && ok=1 ;; esac
  printf '%-34s 期待 rc=%-3s 実 rc=%-3s %s\n' "$1" "$2" "$3" "$([ $ok = 1 ] && echo OK || echo '<<< 期待外れ')"
  [ $ok = 1 ] || NG=$((NG + 1))
}
J() { python3 ctlvfx/judge.py "$1" > "$N/judge.out" 2>&1; echo $?; }

# --- judge.py ---  (基準 $S = 実測 status.csv の全行を合格値にそろえたもの。 実測そのものの判定は J00 に情報として出す)
expect "J0  対照 (全行を合格値にそろえた基準)" 0 "$(J $S)"
echo "J00 実測 status.csv の judge: rc=$(J $S0) ($(tail -n 1 $N/judge.out))"
B=19096   # Fruity dB meter (最小の閉包)
$M csv-set $S $N/a.csv $B emcc_c_rc 1;            expect "J1  emcc_c_rc=1" nz "$(J $N/a.csv)"; grep -q "emcc_c_rc=1" $N/judge.out || { echo "J1 の説明に emcc_c_rc=1 が無い"; NG=$((NG + 1)); }
$M csv-set $S $N/a.csv $B lift_rc 1;              expect "J2  lift_rc=1" nz "$(J $N/a.csv)"
$M csv-set $S $N/a.csv $B f80_funcs 3;            expect "J3  f80_funcs=3" nz "$(J $N/a.csv)"
$M csv-set $S $N/a.csv $B declares_unimpl 5;      expect "J4  declares_unimpl=5" nz "$(J $N/a.csv)"
$M csv-set $S $N/a.csv $B declares_unimpl -1;     expect "J5  declares_unimpl=-1 (simd.log 無し)" nz "$(J $N/a.csv)"
$M csv-set $S $N/a.csv $B defines 6;              expect "J6  defines=6 (closure_funcs=7)" nz "$(J $N/a.csv)"
$M csv-set $S $N/a.csv $B f80_funcs -1;           expect "J7  f80_funcs=-1 (final.ll 無し)" nz "$(J $N/a.csv)"
$M csv-drop $S $N/a.csv $B;                       expect "J8  1 本の行が無い" nz "$(J $N/a.csv)"
$M csv-append $S $N/a.csv '99999,Nonexistent,1,1,0,1,0,0,0,1'; expect "J9  targets に無い block の行" nz "$(J $N/a.csv)"
$M csv-set $S $N/a.csv $B seconds x;              expect "J10 数値でない欄" nz "$(J $N/a.csv)"
$M csv-header $S $N/a.csv;                        expect "J11 header 不一致" nz "$(J $N/a.csv)"
$M csv-set $S $N/a.csv $B name Wrong;             expect "J12 name 不一致" nz "$(J $N/a.csv)"
$M csv-late-fix $S $N/a.csv $B;                   expect "J13 不合格行の後に合格行 (再実行で直った)" 0 "$(J $N/a.csv)"
expect "J14 入力ファイル無し" 2 "$(J $N/none.csv)"

# --- e2e の判定部 (exit が伝わるか) ---
bash ctlvfx/ctlvfx_e2e.sh --judge-only $S > $N/e2e_ok.out 2>&1; r=$?
expect "E0  対照 (--judge-only 合格 CSV)" 0 $r; grep -q '^\[ctlvfx_e2e\] OK' $N/e2e_ok.out || { echo "E0: OK 行が出ていない"; NG=$((NG + 1)); }
$M csv-set $S $N/bad.csv $B emcc_c_rc 1
bash ctlvfx/ctlvfx_e2e.sh --judge-only $N/bad.csv > $N/e2e_bad.out 2>&1; r=$?
expect "E1  --judge-only 不合格 CSV (emcc_c_rc=1)" nz $r; grep -q '^\[ctlvfx_e2e\] OK' $N/e2e_bad.out && { echo "E1: 不合格なのに OK 行が出た"; NG=$((NG + 1)); }

# --- matrix_check.py ---
mc() { python3 ctlvfx/matrix_check.py "$@" > $N/mc.out 2>&1; echo $?; }
expect "M0  対照 (実測 facts)" 0 "$(mc $F)"
$M facts-bump $F $N/f.json "Fruity dB meter" closure_funcs; expect "M1  closure_funcs +1" nz "$(mc $N/f.json)"; grep -q 'MISMATCH Fruity dB meter closure_funcs' $N/mc.out || { echo "M1: 該当 MISMATCH 行が無い"; NG=$((NG + 1)); }
$M facts-bump $F $N/f.json "Wave Candy" vcall;              expect "M2  vcall +1" nz "$(mc $N/f.json)"
$M facts-drop $F $N/f.json "Tuner";                         expect "M3  facts から 1 本欠落" nz "$(mc $N/f.json)"
$M matrix-tier PLUGIN_MATRIX.json $N/m.json "VFX Script"
expect "M4  PLUGIN_MATRIX の Tier を変更" nz "$(mc $F $N/m.json)"

# --- ids_crosscheck.py ---
ic() { python3 ctlvfx/ids_crosscheck.py "$@" > $N/ic.out 2>&1; echo $?; }
expect "I0  対照 (実測 facts)" 0 "$(ic $F)"
$M facts-bump-id $F $N/f.json > $N/ic_who.txt;               expect "I1  taint 側 ID 件数 +1 ($(cat $N/ic_who.txt))" nz "$(ic $N/f.json)"
$M facts-drop $F $N/f.json "Wave Candy";                     expect "I2  facts から 1 本欠落" nz "$(ic $N/f.json)"

# --- closure_defs.py ---
cdef() { python3 ctlvfx/closure_defs.py "$@" > $N/cd.out 2>&1; echo $?; }
expect "D0  対照 (実測 work/batch)" 0 "$(cdef work/batch)"
mkdir -p $N/batch; for d in work/batch/[0-9]*; do ln -s "$PWD/$d" $N/batch/$(basename $d); done
rm $N/batch/$B; mkdir $N/batch/$B
$M ll-rename work/batch/$B/p.final.ll $N/batch/$B/p.final.ll;  expect "D1  define を 1 つ別名に (脱落)" nz "$(cdef $N/batch)"; grep -q "Fruity dB meter.*NG" $N/cd.out || { echo "D1: dB meter の NG 行が無い"; NG=$((NG + 1)); }
$M ll-outside work/batch/$B/p.final.ll $N/batch/$B/p.final.ll; expect "D2  閉包外の define を混入" nz "$(cdef $N/batch)"
rm $N/batch/$B/p.final.ll;                                     expect "D3  final.ll 無し" nz "$(cdef $N/batch)"

# --- lift 本体 (dB meter 19096) ---
OUT=work/batch/$B
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc_rc() { ( TMPDIR="$N/tmp" emcc -c "$1" -o "$N/x.o" -w -O0 -msimd128 > "$N/emcc.log" 2>&1 ); echo $?; }
python3 - "$OUT/p.final.ll" "$N/broken.ll" <<'PY'
import sys
s = open(sys.argv[1]).read()
i = s.index('\ndefine ')
j = s.index('\n}\n', i)
body = s[i:j]
k = body.rindex('\n  ret ')
open(sys.argv[2], 'w').write(s[:i] + body[:k] + s[j:])
PY
expect "L1a 対照 final.ll の emcc -c" 0 "$(emcc_rc $OUT/p.final.ll)"
expect "L1b ret 除去 final.ll の emcc -c" nz "$(emcc_rc $N/broken.ll)"
R=work/closure/block$(printf %05d $B).ranges.txt
n_all=$(tr ',' '\n' < "$R" | wc -l)
LAST=$(tr ',' '\n' < "$R" | tail -n 1 | cut -d- -f1 | sed 's/^0x//')
d0=$(grep -c '^define' "$OUT/p.final.ll"); h0=$(grep -c "^define .*@function_$LAST\\b" "$OUT/p.final.ll")
tr ',' '\n' < "$R" | head -n $((n_all - 1)) | paste -sd, > "$N/ranges_minus1.txt"
bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin" "$N/ranges_minus1.txt" "$N/lift" p 600 > "$N/lift.log" 2>&1
d1=$(grep -c '^define' "$N/lift/p.final.ll"); h1=$(grep -c "^define .*@function_$LAST\\b" "$N/lift/p.final.ll")
echo "L2  ranges $n_all -> $((n_all - 1)), 落とした関数 function_$LAST: 対照 define=$d0 present=$h0 / 1 つ落とした後 define=$d1 present=$h1"
expect "L2a 落とした関数が対照に在る" 1 "$h0"
expect "L2b 落とした関数が消える" 0 "$h1"
[ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ] || { echo "L2c: define 数が減っていない / 0"; NG=$((NG + 1)); }

if [ "$NG" -ne 0 ]; then echo "[ctlvfx_nega] FAIL: 期待外れ $NG 件" >&2; exit 1; fi
echo "[ctlvfx_nega] OK"
