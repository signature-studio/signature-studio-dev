#!/usr/bin/env bash
# g1_e2e.sh の各 gate の識別力を確認するネガティブコントロール (NC)。 各 NC は「対照 (無改変) は合格 / 壊した入力は不合格」の両方を確認する。
#   bash tools/plugins/g1/g1_nega.sh      (事前: g1_e2e.sh を実行済み = work/batch, work/closure, work/g1)
# exit 0 = 全 NC が DETECTED。 1 つでも NOT DETECTED なら exit 1 (最終行 `[g1_nega] OK` は出さない)。
#   NC1 emcc -c        : final.ll の定義 1 つの ret を除去 → rc 非 0 (対照 rc 0)
#   NC2 ranges         : 閉包 ranges の末尾 1 つを落として再 lift → その function_<VA> が final.ll から消える (対照は在る)
#   NC3 judge.py       : 実測 status.csv を 1 箇所ずつ壊した全変異を拒否 (judge_nc.py)
#   NC4 e2e の終了コード: 不合格行を入れた status.csv で g1_e2e.sh --skip-lift --judge-only → 非 0 で、`[g1_e2e]` の通過行を出さない
#   NC5 matrix_check   : facts の closure_funcs を +1 / plugin を 1 本欠く / 空 → 非 0
#   NC6 ids_crosscheck : facts の Dispatcher ID 件数を +1 / 空 → 非 0
#   NC7 icall_check    : audit JSON の静的 site を +1 / JSON を欠く → 非 0
#   NC8 engine_check   : engines.csv の行を 1 つ欠く / 非整数 → 非 0
#   NC9 define_audit   : final.ll の閉包関数 1 つの define 名を変える / final.ll を欠く → 非 0 (対照 rc 0)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
N=work/g1/nega; rm -rf "$N"; mkdir -p "$N/tmp"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
read -r -a BLOCKS <<< "$(python3 g1/common.py shells)"
read -r -a CPP <<< "$(python3 g1/common.py engines)"
FAIL=0
verdict() { # name ok(0/1) detail
  if [ "$2" = 0 ]; then echo "$1: DETECTED  $3"; else echo "$1: NOT DETECTED  $3"; FAIL=1; fi
}
rc_of() { "$@" > "$N/last.out" 2> "$N/last.err"; echo $?; }
emcc_rc() { ( TMPDIR="$N/tmp" emcc -c "$1" -o "$N/x.o" -w -O0 -msimd128 > "$N/emcc.log" 2>&1 ); echo $?; }

# --- NC1 / NC2 (Wasp 24302: 最小の閉包 = 9 関数)
B=24302; OUT=work/batch/$B
c0=$(emcc_rc "$OUT/p.final.ll")
python3 - "$OUT/p.final.ll" "$N/broken.ll" <<'PY'
import sys
s = open(sys.argv[1]).read()
i = s.index('\ndefine ')
j = s.index('\n}\n', i)
body = s[i:j]
k = body.rindex('\n  ret ')
open(sys.argv[2], 'w').write(s[:i] + body[:k] + s[j:])
PY
c1=$(emcc_rc "$N/broken.ll")
verdict "NC1 emcc -c" $([ "$c0" = 0 ] && [ "$c1" != 0 ]; echo $?) "対照 rc=$c0 / ret 除去 rc=$c1 (期待 0 / 非0)"

R=work/closure/block$(printf %05d $B).ranges.txt
n_all=$(tr ',' '\n' < "$R" | wc -l)
LAST=$(tr ',' '\n' < "$R" | tail -n 1 | cut -d- -f1 | sed 's/^0x//')
d0=$(grep -c '^define' "$OUT/p.final.ll"); h0=$(grep -c "^define .*@function_$LAST\\b" "$OUT/p.final.ll")
tr ',' '\n' < "$R" | head -n $((n_all - 1)) | paste -sd, > "$N/ranges_minus1.txt"
bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin" "$N/ranges_minus1.txt" "$N/lift" p 600 > "$N/lift.log" 2>&1
d1=$(grep -c '^define' "$N/lift/p.final.ll"); h1=$(grep -c "^define .*@function_$LAST\\b" "$N/lift/p.final.ll" || true)
verdict "NC2 ranges" $([ "$h0" = 1 ] && [ "$h1" = 0 ] && [ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ]; echo $?) \
  "ranges $n_all -> $((n_all - 1)), 落とした function_$LAST: 対照 define=$d0 present=$h0 / minus1 define=$d1 present=$h1"

# --- NC3 judge.py (実測 status.csv の全変異)
python3 g1/judge_nc.py work/g1/status12.csv "${BLOCKS[@]}" | tee "$N/nc3.txt"; nc3=${PIPESTATUS[0]}
verdict "NC3 judge.py" "$nc3" "$(grep '^変異' "$N/nc3.txt")"

# --- NC4 e2e の終了コード
cp work/batch/status.csv "$N/status_ctl.csv"
python3 - work/batch/status.csv "$N/status_bad.csv" <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1])))
rows[1][8] = '1'            # 先頭 block の emcc_c_rc を 1 に
csv.writer(open(sys.argv[2], 'w')).writerows(rows)
PY
rc_ctl=$(G1_STATUS_CSV="$N/status_ctl.csv" rc_of bash g1/g1_e2e.sh --skip-lift --judge-only); grep -c 'judge-only: gate 1 のみ通過' "$N/last.out" > "$N/ctl_pass_lines"
rc_bad=$(G1_STATUS_CSV="$N/status_bad.csv" rc_of bash g1/g1_e2e.sh --skip-lift --judge-only); pass_bad=$(grep -c 'judge-only: gate 1 のみ通過\|\[g1_e2e\] OK' "$N/last.out" || true)
verdict "NC4 e2e exit code" $([ "$rc_ctl" = 0 ] && [ "$(cat "$N/ctl_pass_lines")" = 1 ] && [ "$rc_bad" != 0 ] && [ "$pass_bad" = 0 ]; echo $?) \
  "対照 rc=$rc_ctl (通過行 $(cat "$N/ctl_pass_lines")) / emcc_c_rc=1 注入 rc=$rc_bad (通過行 $pass_bad)"

# --- NC5 matrix_check / NC6 ids_crosscheck (facts を壊す)
python3 - work/g1/facts.json "$N" <<'PY'
import json, sys, copy
f = json.load(open(sys.argv[1])); d = sys.argv[2]
json.dump(f, open(d + '/facts_ctl.json', 'w'))
g = copy.deepcopy(f); g['BassDrum']['closure_funcs'] += 1; json.dump(g, open(d + '/facts_m_plus1.json', 'w'))
g = copy.deepcopy(f); del g['Fruit Kick']; json.dump(g, open(d + '/facts_m_drop.json', 'w'))
json.dump({}, open(d + '/facts_empty.json', 'w'))
g = copy.deepcopy(f)
for name, p in g.items():
    ids = {k: v for k, v in p['host']['ids'].items() if k != 'dyn'}
    if ids:
        k = next(iter(ids)); p['host']['ids'][k] += 1; print('ids +1:', name, 'ID', k, '->', p['host']['ids'][k]); break
json.dump(g, open(d + '/facts_i_plus1.json', 'w'))
PY
r0=$(rc_of python3 g1/matrix_check.py "$N/facts_ctl.json"); m1=$(rc_of python3 g1/matrix_check.py "$N/facts_m_plus1.json"); m2=$(rc_of python3 g1/matrix_check.py "$N/facts_m_drop.json"); m3=$(rc_of python3 g1/matrix_check.py "$N/facts_empty.json")
verdict "NC5 matrix_check" $([ "$r0" = 0 ] && [ "$m1" != 0 ] && [ "$m2" != 0 ] && [ "$m3" != 0 ]; echo $?) "対照 rc=$r0 / closure_funcs+1 rc=$m1 / plugin 欠落 rc=$m2 / 空 rc=$m3"
i0=$(rc_of python3 g1/ids_crosscheck.py "$N/facts_ctl.json"); i1=$(rc_of python3 g1/ids_crosscheck.py "$N/facts_i_plus1.json"); i2=$(rc_of python3 g1/ids_crosscheck.py "$N/facts_empty.json")
verdict "NC6 ids_crosscheck" $([ "$i0" = 0 ] && [ "$i1" != 0 ] && [ "$i2" != 0 ]; echo $?) "対照 rc=$i0 / ID 件数+1 rc=$i1 / 空 rc=$i2"

# --- NC7 icall_check (audit JSON を壊す)
mkdir -p "$N/icall_ctl" "$N/icall_plus1" "$N/icall_missing"
cp work/g1/icall/*.icall.json "$N/icall_ctl/"; cp work/g1/icall/*.icall.json "$N/icall_plus1/"; cp work/g1/icall/*.icall.json "$N/icall_missing/"
python3 - "$N/icall_plus1/${BLOCKS[0]}.icall.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1])); j['call_non_iat'] += 1; json.dump(j, open(sys.argv[1], 'w'))
PY
rm "$N/icall_missing/${BLOCKS[1]}.icall.json"
c0=$(rc_of python3 g1/icall_check.py --json-dir "$N/icall_ctl" "${BLOCKS[@]}"); c1=$(rc_of python3 g1/icall_check.py --json-dir "$N/icall_plus1" "${BLOCKS[@]}"); c2=$(rc_of python3 g1/icall_check.py --json-dir "$N/icall_missing" "${BLOCKS[@]}")
verdict "NC7 icall_check" $([ "$c0" = 0 ] && [ "$c1" != 0 ] && [ "$c2" != 0 ]; echo $?) "対照 rc=$c0 / 静的 site+1 rc=$c1 / JSON 欠落 rc=$c2"

# --- NC8 engine_check
if [ -f work/g1/engines.csv ]; then
  e0=$(rc_of python3 g1/engine_check.py work/g1/engines.csv "${CPP[@]}")
  sed '$d' work/g1/engines.csv > "$N/eng_drop.csv"
  e1=$(rc_of python3 g1/engine_check.py "$N/eng_drop.csv" "${CPP[@]}")
  awk -F, 'BEGIN{OFS=","} NR==2{$3="x"} {print}' work/g1/engines.csv > "$N/eng_nan.csv"
  e2=$(rc_of python3 g1/engine_check.py "$N/eng_nan.csv" "${CPP[@]}")
  verdict "NC8 engine_check" $([ "$e0" = 0 ] && [ "$e1" != 0 ] && [ "$e2" != 0 ]; echo $?) "対照 rc=$e0 / 末尾行欠落 rc=$e1 / 非整数 rc=$e2"
else
  verdict "NC8 engine_check" 1 "work/g1/engines.csv が無い (g1_e2e.sh を --skip-engines 無しで実行すること)"
fi

# --- NC9 define_audit
mkdir -p "$N/batch_ctl/21148" "$N/batch_ren/21148" "$N/batch_none"
cp work/batch/21148/p.final.ll "$N/batch_ctl/21148/"
V=$(tr ',' '\n' < work/closure/block21148.ranges.txt | head -n 1 | cut -d- -f1 | sed 's/^0x//')
sed "s/^\(define [^@]*@function_\)$V\b/\1ffffff/" work/batch/21148/p.final.ll > "$N/batch_ren/21148/p.final.ll"
a0=$(rc_of python3 g1/define_audit.py --batch-dir "$N/batch_ctl" 21148); a1=$(rc_of python3 g1/define_audit.py --batch-dir "$N/batch_ren" 21148); a2=$(rc_of python3 g1/define_audit.py --batch-dir "$N/batch_none" 21148)
verdict "NC9 define_audit" $([ "$a0" = 0 ] && [ "$a1" != 0 ] && [ "$a2" != 0 ]; echo $?) "対照 rc=$a0 / function_$V を function_ffffff に改名 rc=$a1 / final.ll 無し rc=$a2"

if [ "$FAIL" = 0 ]; then echo "[g1_nega] OK"; exit 0; fi
echo "[g1_nega] FAIL" >&2; exit 1
