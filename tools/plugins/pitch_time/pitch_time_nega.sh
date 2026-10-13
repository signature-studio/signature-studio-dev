#!/usr/bin/env bash
# pitch_time_e2e.sh の各 gate の識別力を確認するネガティブコントロール。 全て「期待した終了コードになること」を数値で確認し、
# 1 つでも外れたら exit 1。 事前: pitch_time_e2e.sh を実行済み (work/pitch_time/{status7.csv,facts.json,cpp.csv}, work/batch/19087)。
#   NC1  emcc -c ゲート       : Fruity Vocoder (19087, 最小の殻) の final.ll の関数 1 つの ret を除去 → emcc -c が非 0 (対照: 無改変は 0)
#   NC2  ranges が lift 範囲を決める : 閉包 ranges の末尾 1 つを落として再 lift → その function_<VA> の define が消える (対照: ある)
#   NC3  judge.py (shell 判定) : 実測 status7.csv / final.ll / ranges から不合格を 1 つずつ作り、期待終了コードを確認 (対照 = 無改変 → 0)
#   NC4  e2e の配線           : `pitch_time_e2e.sh --judge-only` に不合格の status CSV / cpp CSV を渡し、非 0 かつ PASS 行が出ないこと
#   NC5  matrix_check.py      : facts.json / status7.csv を 1 項目ずつ壊し exit 1 (対照 → 0)
#   NC6  ids_crosscheck.py    : taint 側の ID 件数を +1 / ID を空にして exit 1 (対照 → 0)
#   NC7  judge.py --engines   : expected_cpp.csv の 1 値を変えて exit 1 (対照 → 0)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
W=work/pitch_time; N=$W/nega; rm -rf "$N"; mkdir -p "$N/tmp"
SHELLS=(19071 19087 19098 19166 19217 19221 19270)
FAILS=0
chk() {   # chk <name> <expected_rc> <cmd...>   : 実終了コードを表示し、期待と違えば FAIL
  local name="$1" want="$2"; shift 2
  "$@" > "$N/$name.out" 2>&1; local rc=$?
  if [ "$rc" = "$want" ]; then echo "  $name: rc=$rc (期待 $want) OK"; else echo "  $name: rc=$rc (期待 $want) <-- FAIL"; FAILS=$((FAILS + 1)); fi
}
mut() {   # mut <in.csv> <out.csv> <block|-> <col> <val|DROP>  : 1 行の 1 列を書き換える / 行を削除する
  python3 - "$@" <<'PY'
import csv, sys
src, dst, blk, col, val = sys.argv[1:6]
rows = list(csv.reader(open(src)))
hdr, body = rows[0], rows[1:]
out = []
for r in body:
    if r[0] == blk:
        if val == 'DROP':
            continue
        r = list(r); r[hdr.index(col)] = val
    out.append(r)
csv.writer(open(dst, 'w')).writerows([hdr] + out)
PY
}
S0=$W/status7.csv
[ -f "$S0" ] || { echo "[pitch_time_nega] $S0 が無い (先に pitch_time_e2e.sh)" >&2; exit 1; }
J="python3 pitch_time/judge.py"

echo "NC1/NC2: lift 経路 (Fruity Vocoder 19087)"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
B=19087; OUT=work/batch/$B
emcc_rc() { ( TMPDIR="$N/tmp" emcc -c "$1" -o "$N/x.o" -w -O0 -msimd128 > "$N/emcc.log" 2>&1 ); echo $?; }
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
echo "  NC1: emcc -c control(rc)=$c0 broken(rc)=$c1 (期待: 0 / 非0)"
R=work/closure/block$(printf %05d $B).ranges.txt
n_all=$(tr ',' '\n' < "$R" | wc -l)
LAST=$(tr ',' '\n' < "$R" | tail -n 1 | cut -d- -f1 | sed 's/^0x//')
d0=$(grep -c '^define' "$OUT/p.final.ll"); h0=$(grep -c "^define .*@function_$LAST\\b" "$OUT/p.final.ll")
tr ',' '\n' < "$R" | head -n $((n_all - 1)) | paste -sd, > "$N/ranges_minus1.txt"
bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin" "$N/ranges_minus1.txt" "$N/lift" p 600 > "$N/lift.log" 2>&1
d1=$(grep -c '^define' "$N/lift/p.final.ll"); h1=$(grep -c "^define .*@function_$LAST\\b" "$N/lift/p.final.ll" || true)
echo "  NC2: ranges $n_all -> $((n_all - 1)), 落とした関数 function_$LAST: control define=$d0 present=$h0 / minus1 define=$d1 present=$h1 (期待: present 1 -> 0, define 減)"
{ [ "$c0" = 0 ] && [ "$c1" != 0 ] && [ "$h0" = 1 ] && [ "$h1" = 0 ] && [ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ]; } || { echo "  NC1/NC2 <-- FAIL"; FAILS=$((FAILS + 1)); }

echo "NC3: judge.py (shell 判定)。 Fruity Scratcher 19071 / Newtime 19166 を壊す"
JA="--closure-dir work/closure --ll-dir work/batch"
chk NC3-control 0 $J "$S0" "${SHELLS[@]}" $JA
mut "$S0" "$N/a.csv" 19071 emcc_c_rc 1;            chk NC3-a-emcc_c_rc1 1 $J "$N/a.csv" "${SHELLS[@]}" $JA
mut "$S0" "$N/b.csv" 19071 lift_rc 1;              chk NC3-b-lift_rc1 1 $J "$N/b.csv" "${SHELLS[@]}" $JA
mut "$S0" "$N/c.csv" 19166 f80_funcs 3;            chk NC3-c-f80_funcs3 1 $J "$N/c.csv" "${SHELLS[@]}" $JA
mut "$S0" "$N/d.csv" 19166 declares_unimpl 5;      chk NC3-d-declares_unimpl5 1 $J "$N/d.csv" "${SHELLS[@]}" $JA
mut "$S0" "$N/f.csv" 19166 x DROP;                 chk NC3-f-row_missing 1 $J "$N/f.csv" "${SHELLS[@]}" $JA
mut "$S0" "$N/g.csv" 19166 f80_funcs -1;           chk NC3-g-f80_unmeasured 1 $J "$N/g.csv" "${SHELLS[@]}" $JA
mut "$S0" "$N/h.csv" 19166 emcc_c_rc x;            chk NC3-h-non_numeric 2 $J "$N/h.csv" "${SHELLS[@]}" $JA
chk NC3-i-no_blocks 2 $J "$S0" $JA
chk NC3-j-stale_rows_ignored 1 $J "$S0" "${SHELLS[@]}" $JA --since-line "$(wc -l < "$S0")"
chk NC3-k-no_file 2 $J "$N/none.csv" "${SHELLS[@]}" $JA
chk NC3-l-no_audit_args 2 $J "$S0" "${SHELLS[@]}"
# e: 欠落監査。 Newtime の final.ll で最後の range の define 名を変えて「関数が 1 つ脱落した」状態を作る (他の block は実物へのリンク)
mkdir -p "$N/ll"
for b in "${SHELLS[@]}"; do mkdir -p "$N/ll/$b"; ln -sf "$PWD/work/batch/$b/p.final.ll" "$N/ll/$b/p.final.ll"; done
LASTN=$(tr ',' '\n' < work/closure/block19166.ranges.txt | tail -n 1 | cut -d- -f1 | sed 's/^0x//')
rm "$N/ll/19166/p.final.ll"; sed "s/^\(define [^@]*\)@function_$LASTN\b/\1@lost_$LASTN/" work/batch/19166/p.final.ll > "$N/ll/19166/p.final.ll"
echo "  (e: 19166 の function_$LASTN を脱落させた final.ll: define $(grep -c '^define' work/batch/19166/p.final.ll) -> $(grep -c '^define .*@function_' "$N/ll/19166/p.final.ll"))"
chk NC3-e-define_lost 1 $J "$S0" "${SHELLS[@]}" --closure-dir work/closure --ll-dir "$N/ll"
# m: ranges.txt と status の closure_funcs が食い違う (range を 1 つ足す)
mkdir -p "$N/closure"; cp work/closure/block*.ranges.txt "$N/closure/"
echo -n ",0x1000-0x1001" >> "$N/closure/block19166.ranges.txt"
chk NC3-m-ranges_ne_closure_funcs 1 $J "$S0" "${SHELLS[@]}" --closure-dir "$N/closure" --ll-dir work/batch

echo "NC4: pitch_time_e2e.sh --judge-only の配線 (不合格 CSV を STATUS_CSV で渡す)"
STATUS_CSV="$N/a.csv" bash pitch_time/pitch_time_e2e.sh --judge-only > "$N/e2e_bad.out" 2>&1; rc=$?
if [ "$rc" != 0 ] && ! grep -q 'PASS$' "$N/e2e_bad.out" && grep -q 'FAIL (exit' "$N/e2e_bad.out"; then echo "  NC4-bad: rc=$rc (期待 非0)、PASS 行なし、FAIL 行あり OK"; else echo "  NC4-bad: rc=$rc <-- FAIL"; FAILS=$((FAILS + 1)); fi
STATUS_CSV="$S0" bash pitch_time/pitch_time_e2e.sh --judge-only > "$N/e2e_good.out" 2>&1; rc=$?
if [ "$rc" = 0 ] && grep -q 'JUDGE-ONLY PASS$' "$N/e2e_good.out"; then echo "  NC4-good: rc=$rc (期待 0)、PASS 行あり OK"; else echo "  NC4-good: rc=$rc <-- FAIL"; FAILS=$((FAILS + 1)); fi

# C++ module の judge --engines の配線: 測定値を 1 つ変えた cpp.csv を CPP_CSV で渡す
python3 - "$W/cpp.csv" "$N/cpp_bad.csv" <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1])))
i = rows[0].index('emcc_c_fail_chunks'); rows[1][i] = str(1 - int(rows[1][i]))
csv.writer(open(sys.argv[2], 'w', newline=''), lineterminator='\n').writerows(rows)
PY
STATUS_CSV="$S0" CPP_CSV="$N/cpp_bad.csv" bash pitch_time/pitch_time_e2e.sh --judge-only > "$N/e2e_badcpp.out" 2>&1; rc=$?
if [ "$rc" != 0 ] && ! grep -q 'PASS$' "$N/e2e_badcpp.out" && grep -q 'FAIL (exit' "$N/e2e_badcpp.out"; then echo "  NC4-badcpp: rc=$rc (期待 非0)、PASS 行なし、FAIL 行あり OK"; else echo "  NC4-badcpp: rc=$rc <-- FAIL"; FAILS=$((FAILS + 1)); fi

echo "NC5: matrix_check.py"
chk NC5-control 0 python3 pitch_time/matrix_check.py
python3 - "$W/facts.json" "$N/facts_m.json" <<'PY'
import json, sys
f = json.load(open(sys.argv[1])); f['shells']['Newtime']['closure_funcs'] += 1
json.dump(f, open(sys.argv[2], 'w'))
PY
chk NC5-a-closure_funcs_plus1 1 python3 pitch_time/matrix_check.py --facts "$N/facts_m.json"
mut "$S0" "$N/s_m.csv" 19087 emcc_c_rc 1
chk NC5-b-batch_Vocoder_emcc_c_rc1 1 python3 pitch_time/matrix_check.py --status "$N/s_m.csv"
python3 -c "
import json; f=json.load(open('$W/facts.json')); f['shells']={}; json.dump(f, open('$N/facts_empty.json','w'))"
chk NC5-c-zero_shells 1 python3 pitch_time/matrix_check.py --facts "$N/facts_empty.json"

echo "NC6: ids_crosscheck.py"
chk NC6-control 0 python3 pitch_time/ids_crosscheck.py
python3 - "$W/facts.json" "$N/facts_i.json" "$N/facts_i0.json" <<'PY'
import json, sys
f = json.load(open(sys.argv[1]))
for n, p in f['shells'].items():
    ids = [k for k in p['host']['ids'] if k != 'dyn']
    if ids:
        p['host']['ids'][ids[0]] += 1
        print('perturbed', n, ids[0], file=sys.stderr)
        break
json.dump(f, open(sys.argv[2], 'w'))
f = json.load(open(sys.argv[1]))
for p in f['shells'].values():
    p['host']['ids'] = {}
json.dump(f, open(sys.argv[3], 'w'))
PY
chk NC6-a-taint_id_plus1 1 python3 pitch_time/ids_crosscheck.py --facts "$N/facts_i.json"
chk NC6-b-empty_ids 1 python3 pitch_time/ids_crosscheck.py --facts "$N/facts_i0.json"

echo "NC7: judge.py --engines"
CPP=$W/cpp.csv; EXPC=pitch_time/expected_cpp.csv
chk NC7-control 0 $J --engines "$CPP" "$EXPC" 19222 19072
python3 - "$EXPC" "$N/exp_bad.csv" <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1])))
i = rows[0].index('emcc_c_fail_chunks'); rows[1][i] = str(int(rows[1][i]) + 1)
csv.writer(open(sys.argv[2], 'w')).writerows(rows)
PY
chk NC7-a-expected_changed 1 $J --engines "$CPP" "$N/exp_bad.csv" 19222 19072
head -n 2 "$CPP" > "$N/cpp_short.csv"
chk NC7-b-row_missing 1 $J --engines "$N/cpp_short.csv" "$EXPC" 19222 19072
chk NC7-c-unknown_block 2 $J --engines "$CPP" "$EXPC" 99999

if [ "$FAILS" = 0 ]; then echo "[pitch_time_nega] OK"; exit 0; fi
echo "[pitch_time_nega] FAIL: $FAILS 件" >&2; exit 1
