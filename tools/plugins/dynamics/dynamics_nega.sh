#!/usr/bin/env bash
# dynamics_e2e.sh の判定の識別力を確認するネガティブコントロール (Fruity Limiter block 19021, 最小の閉包)。
#   NC1: final.ll の関数 1 つを壊す (定義の ret を除去) → `emcc -c` が FAIL すること (対照: 無改変は rc=0)
#   NC2: 閉包 ranges の末尾 1 range を落として再 lift → その関数 (function_<start>) が final.ll から消え、他の関数は残ること
#        (対照: 無改変の final.ll には存在する。 RetDec は 1 range から 2 define を出す場合があるため define 数の差は 1 と限らない)
#   NC3: 実測の status7.csv の 1 セルを不合格値にした合成 CSV を judge.py に渡し、 rc 1 で終わること (対照: 無改変は rc 0)。
#        さらに work/batch/status.csv へ不合格行を足して dynamics_e2e.sh --skip-lift を実行し、 exit 非 0 かつ OK 行なしを確認 (終了時に元へ戻す)
# 事前: dynamics_e2e.sh を実行済み (work/batch/19021 と work/dynamics/status7.csv がある)。 exit 0 = 全部 期待通り
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B=19021
OUT=work/batch/$B
N=work/dynamics/nega; rm -rf "$N"; mkdir -p "$N/tmp"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1

emcc_rc() { ( TMPDIR="$N/tmp" emcc -c "$1" -o "$N/x.o" -w -O0 -msimd128 > "$N/emcc.log" 2>&1 ); echo $?; }

c0=$(emcc_rc "$OUT/p.final.ll")
python3 - "$OUT/p.final.ll" "$N/broken.ll" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
i = s.index('\ndefine ')
j = s.index('\n}\n', i)            # 最初の関数の閉じ括弧
body = s[i:j]
k = body.rindex('\n  ret ')        # その最後の ret を除去 (終端命令欠落 = 不正 IR)
open(sys.argv[2], 'w').write(s[:i] + body[:k] + s[j:])
PY
c1=$(emcc_rc "$N/broken.ll")
echo "NC1: emcc -c  control(rc)=$c0  broken(rc)=$c1  (期待: 0 / 非0)"

R=work/closure/block$(printf %05d $B).ranges.txt
n_all=$(tr ',' '\n' < "$R" | wc -l)
LAST=$(tr ',' '\n' < "$R" | tail -n 1 | cut -d- -f1 | sed 's/^0x//')
d0=$(grep -c '^define' "$OUT/p.final.ll"); h0=$(grep -c "^define .*@function_$LAST\\b" "$OUT/p.final.ll")
tr ',' '\n' < "$R" | head -n $((n_all - 1)) | paste -sd, > "$N/ranges_minus1.txt"
bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin" "$N/ranges_minus1.txt" "$N/lift" p 600 > "$N/lift.log" 2>&1
d1=$(grep -c '^define' "$N/lift/p.final.ll"); h1=$(grep -c "^define .*@function_$LAST\\b" "$N/lift/p.final.ll" || true)
echo "NC2: ranges $n_all -> $((n_all - 1)), 落とした関数 function_$LAST:  control: define=$d0 present=$h0 / minus1: define=$d1 present=$h1  (期待: 1 -> 0, define 減)"

S7=work/dynamics/status7.csv
ST=work/batch/status.csv
cp "$S7" "$N/status7.orig.csv"; cp "$ST" "$N/status.orig.csv"
trap 'cp "$N/status7.orig.csv" "$S7"; cp "$N/status.orig.csv" "$ST"' EXIT
mapfile -t BL < <(tail -n +2 "$S7" | cut -d, -f1)
[ "${#BL[@]}" = 7 ] || { echo "[dynamics_nega] FAIL: $S7 の行が 7 本でない (${#BL[@]})" >&2; exit 1; }
python3 - "$S7" "$N" <<'PY'
import csv, sys
with open(sys.argv[1], newline='') as f:
    rows = list(csv.reader(f))
hdr, body = rows[0], rows[1:]
col = {c: i for i, c in enumerate(hdr)}
def mk(name, edit):
    b = [list(r) for r in body]
    edit(b)
    with open('%s/nc3_%s.csv' % (sys.argv[2], name), 'w', newline='') as f:
        csv.writer(f).writerows([hdr] + b)
def setv(block, **kv):
    def f(b):
        for r in b:
            if r[col['block']] == block:
                for k, v in kv.items():
                    r[col[k]] = v
    return f
mk('control', lambda b: None)
mk('emcc', setv('19021', emcc_c_rc='1'))
mk('lift_f80', setv('19021', lift_rc='1', f80_funcs='3'))
mk('unimpl', setv('19148', declares_unimpl='5'))
mk('unmeasured', setv('18990', declares_unimpl='-1'))
mk('drop', lambda b: b.pop())
PY
NC3_RC=()
nc3() {   # $1=ラベル $2=合成 CSV → judge.py の rc と「rows= bad=」要約を出す
  local out rc=0
  out=$(python3 dynamics/judge.py "$2" "${BL[@]}" 2>&1) || rc=$?
  echo "NC3 $1: judge.py rc=$rc  $(printf '%s\n' "$out" | grep -o 'rows=[0-9/]* bad=[0-9]*' | head -n 1)"
  NC3_RC+=("$rc")
}
nc3 "control (実測 status7.csv そのまま)       (期待 rc 0)" "$N/nc3_control.csv"
nc3 "19021 emcc_c_rc=1                         (期待 rc 1)" "$N/nc3_emcc.csv"
nc3 "19021 lift_rc=1 + f80_funcs=3             (期待 rc 1)" "$N/nc3_lift_f80.csv"
nc3 "19148 declares_unimpl=5                   (期待 rc 1)" "$N/nc3_unimpl.csv"
nc3 "18990 declares_unimpl=-1 (未計測)         (期待 rc 1)" "$N/nc3_unmeasured.csv"
nc3 "19251 の行を落とす (6/7 行)               (期待 rc 1)" "$N/nc3_drop.csv"
n3=1; [ "${NC3_RC[0]}" = 0 ] || n3=0
for i in 1 2 3 4 5; do [ "${NC3_RC[$i]}" = 1 ] || n3=0; done

row=$(awk -F, -v OFS=, '$1 == 19021 { l = $0 } END { n = split(l, a, ","); a[9] = 1; s = a[1]; for (i = 2; i <= n; i++) s = s OFS a[i]; print s }' "$ST")
echo "$row" >> "$ST"
e2rc=0; bash dynamics/dynamics_e2e.sh --skip-lift > "$N/nc3_e2e.log" 2>&1 || e2rc=$?
e2ok=$(grep -c '^\[dynamics_e2e\] OK' "$N/nc3_e2e.log" || true)
echo "NC3 dynamics_e2e.sh --skip-lift + status.csv に 19021 の emcc_c_rc=1 行を追記 ($row): exit=$e2rc, OK 行=$e2ok 本  (期待 exit 1 / OK 行 0)"
[ "$e2rc" = 1 ] && [ "$e2ok" = 0 ] || n3=0

[ "$c0" = 0 ] && [ "$c1" != 0 ] && [ "$n3" = 1 ] && [ "$h0" = 1 ] && [ "$h1" = 0 ] && [ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ] && { echo "[dynamics_nega] OK"; exit 0; }
echo "[dynamics_nega] FAIL" >&2; exit 1
