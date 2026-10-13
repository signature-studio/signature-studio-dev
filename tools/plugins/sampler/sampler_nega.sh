#!/usr/bin/env bash
# sampler_e2e.sh の各検査の識別力を確認するネガティブコントロール (対照 = 無改変で通ること、壊したものが落ちること)。
#   NC1: final.ll の関数 1 つを壊す (ret 除去) → `emcc -c` が FAIL      (FL Keys block 22386, 最小の閉包)
#   NC2: 閉包 ranges の末尾 1 range を落として再 lift → その関数が final.ll から消え、他は残る
#   NC3: judge.py shells に合成 status.csv を渡す。 不合格行 10 種 (emcc_c_rc / lift_rc / f80 / 未実装 helper 超過・負値・許可外名 / 行欠落 / header のみ) が全て非 0
#   NC4: e2e 本体 (--skip-lift --judge-only) に不合格行を足した status.csv を渡す → 非 0 かつ OK 行が出ない (対照: 無改変 rc 0)
#   NC5: matrix_check.py に壊した facts / status を渡す (閉包値 +1 / 殻欠落 / 空 / batch 値改変) → 非 0
#   NC6: ids_crosscheck.py に taint 側の ID 件数 +1 の facts を渡す → 非 0
#   NC7: judge.py engines に lift_rc=1 / 行欠落の engines.csv を渡す → 非 0
# 事前: sampler_e2e.sh を実行済み。 exit 0 = 全て期待通り
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B=22386
OUT=work/batch/$B
N=work/sampler/nega; rm -rf "$N"; mkdir -p "$N/tmp"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
FAIL=0
expect() { # expect <label> <実測値> <期待>   (一致しなければ FAIL)
  if [ "$2" = "$3" ]; then :; else echo "  !! $1: 実測 $2 / 期待 $3" >&2; FAIL=1; fi
}

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
echo "NC1: emcc -c  control(rc)=$c0  broken(rc)=$c1  (期待: 0 / 非0)"
expect NC1-control "$c0" 0
[ "$c1" != 0 ] || { echo "  !! NC1: broken が rc 0" >&2; FAIL=1; }

R=work/closure/block$(printf %05d $B).ranges.txt
n_all=$(tr ',' '\n' < "$R" | wc -l)
LAST=$(tr ',' '\n' < "$R" | tail -n 1 | cut -d- -f1 | sed 's/^0x//')
d0=$(grep -c '^define' "$OUT/p.final.ll"); h0=$(grep -c "^define .*@function_$LAST\\b" "$OUT/p.final.ll" || true)
tr ',' '\n' < "$R" | head -n $((n_all - 1)) | paste -sd, > "$N/ranges_minus1.txt"
bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin" "$N/ranges_minus1.txt" "$N/lift" p 600 > "$N/lift.log" 2>&1
d1=$(grep -c '^define' "$N/lift/p.final.ll"); h1=$(grep -c "^define .*@function_$LAST\\b" "$N/lift/p.final.ll" || true)
echo "NC2: ranges $n_all -> $((n_all - 1)), 落とした関数 function_$LAST:  control: define=$d0 present=$h0 / minus1: define=$d1 present=$h1  (期待: 1 -> 0, define 減)"
expect NC2-present "$h0 $h1" "1 0"
{ [ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ]; } || { echo "  !! NC2: define 数" >&2; FAIL=1; }

BL="$(python3 sampler/targets.py blocks | tr ' ' ',')"
EL="$(python3 sampler/targets.py engines | tr ' ' ',')"
ALLOW="$(python3 sampler/targets.py allow-unimpl)"
NAMES="$(python3 -c 'import sys; sys.path.insert(0, "sampler"); import targets; print(",".join(targets.ALLOW_UNIMPL_NAMES))')"
J() { python3 sampler/judge.py shells "$1" --blocks "$BL" --allow-unimpl "$ALLOW" --allow-names "$NAMES" > "$N/judge.out" 2>&1; echo $?; }

# 合成: status_run.csv (unimpl_names 列付き) の block/列を書き換える
mut() { # mut <out> <block> <col> <value>   (block=- なら行を消す / col=- なら header のみ残す)
  python3 - "$1" "$2" "$3" "$4" <<'PY'
import csv, sys
out, blk, col, val = sys.argv[1:]
rows = list(csv.reader(open('work/sampler/status_run.csv')))
hdr, body = rows[0], rows[1:]
if col == '-' and blk == '-':
    body = []
elif col == '-':
    body = [r for r in body if r[0] != blk]
else:
    for r in body:
        if r[0] == blk:
            r[hdr.index(col)] = val
csv.writer(open(out, 'w')).writerows([hdr] + body)
PY
}
c=$(J work/sampler/status_run.csv); echo "NC3: judge 対照 (無改変 status_run.csv) rc=$c (期待 0)"; expect NC3-control "$c" 0
RC=""
for spec in "22386 emcc_c_rc 1" "23617 lift_rc 1" "24175 f80_funcs 3" "22386 declares_unimpl 1" "23658 declares_unimpl 2" "23662 declares_unimpl -1" "23658 unimpl_names bogus_helper" "23617 - x" "- - x"; do
  set -- $spec
  mut "$N/j.csv" "$1" "$2" "$3"
  r=$(J "$N/j.csv"); RC="$RC $r"
  echo "NC3: 注入 block=$1 col=$2 val=$3 → rc=$r  ($(tail -n 1 "$N/judge.out"))"
  [ "$r" = 1 ] || { echo "  !! NC3: rc が 1 でない" >&2; FAIL=1; }
done
echo 'not,a,status' > "$N/bad_header.csv"
r=$(J "$N/bad_header.csv"); RC="$RC $r"; echo "NC3: header 不正 → rc=$r (期待 2)"; expect NC3-header "$r" 2
echo "NC3: 注入 10 種の rc =$RC (期待: 1 が 9 つ + 2 が 1 つ)"

# NC4: e2e 本体の終了コード。 work/batch/status.csv に不合格行を足した複製を STATUS_CSV で渡す
cp work/batch/status.csv "$N/status_ok.csv"
cp work/batch/status.csv "$N/status_bad.csv"
echo "22386,FL Keys,29,18986,0,29,0,0,1,2" >> "$N/status_bad.csv"
set +e
STATUS_CSV="$N/status_ok.csv" bash sampler/sampler_e2e.sh --skip-lift --judge-only > "$N/e2e_ok.out" 2>&1; e0=$?
STATUS_CSV="$N/status_bad.csv" bash sampler/sampler_e2e.sh --skip-lift --judge-only > "$N/e2e_bad.out" 2>&1; e1=$?
set -e
okline=$(grep -c 'sampler_e2e\] ' "$N/e2e_bad.out" || true)
echo "NC4: sampler_e2e.sh --skip-lift --judge-only  対照 rc=$e0 / 不合格行(emcc_c_rc=1)を追記 rc=$e1, 不合格側出力の '[sampler_e2e]' 行数=$okline  (期待: 0 / 非0, 0)"
expect NC4-control "$e0" 0
{ [ "$e1" != 0 ] && [ "$okline" = 0 ]; } || { echo "  !! NC4" >&2; FAIL=1; }

# NC5: matrix_check
python3 - <<'PY'
import json, copy, csv
F = json.load(open('work/sampler/facts.json'))
a = copy.deepcopy(F); a['FPC']['closure_funcs'] += 1
b = copy.deepcopy(F); del b['Slicex']
json.dump(a, open('work/sampler/nega/facts_plus1.json', 'w')); json.dump(b, open('work/sampler/nega/facts_missing.json', 'w')); json.dump({}, open('work/sampler/nega/facts_empty.json', 'w'))
rows = list(csv.reader(open('work/sampler/status.csv')))
for r in rows[1:]:
    if r[0] == '22386': r[8] = '1'
csv.writer(open('work/sampler/nega/status_batchmut.csv', 'w')).writerows(rows)
PY
M() { python3 sampler/matrix_check.py "$@" > "$N/mc.out" 2>&1; echo $?; }
m0=$(M); m1=$(M --facts "$N/facts_plus1.json"); m2=$(M --facts "$N/facts_missing.json"); m3=$(M --facts "$N/facts_empty.json"); m4=$(M --status "$N/status_batchmut.csv")
echo "NC5: matrix_check 対照 rc=$m0 / closure_funcs+1 rc=$m1 / 殻欠落 rc=$m2 / 空 facts rc=$m3 / batch 値改変 (FL Keys emcc_c_rc=1) rc=$m4  (期待: 0 / 1 1 1 1)"
expect NC5-control "$m0" 0
expect NC5-broken "$m1 $m2 $m3 $m4" "1 1 1 1"

# NC6: ids_crosscheck (taint 側の ID 件数を +1)
python3 - <<'PY'
import json
F = json.load(open('work/sampler/facts.json'))
for name, f in F.items():
    ids = {k: v for k, v in f.get('host', {}).get('ids', {}).items() if k != 'dyn'}
    if ids:
        k = next(iter(ids))
        f['host']['ids'][k] += 1
        print('NC6 対象:', name, 'ID', k, ids[k], '->', ids[k] + 1)
        break
json.dump(F, open('work/sampler/nega/facts_id_plus1.json', 'w'))
PY
set +e
python3 sampler/ids_crosscheck.py > "$N/ids0.out" 2>&1; i0=$?
python3 sampler/ids_crosscheck.py --facts "$N/facts_id_plus1.json" > "$N/ids1.out" 2>&1; i1=$?
set -e
echo "NC6: ids_crosscheck 対照 rc=$i0 / taint 側 ID +1 rc=$i1  (期待: 0 / 1)"; expect NC6-control "$i0" 0; expect NC6-broken "$i1" 1

# NC7: judge engines
head -n 1 work/sampler/engines.csv > "$N/eng_lift_rc.csv"; tail -n +2 work/sampler/engines.csv | sed '1s/^\([0-9]*,[0-9]*,\)0,/\11,/' >> "$N/eng_lift_rc.csv"
head -n -1 work/sampler/engines.csv > "$N/eng_missing.csv"
JE() { python3 sampler/judge.py engines "$1" --blocks "$EL" > "$N/je.out" 2>&1; echo $?; }
e0=$(JE work/sampler/engines.csv); e1=$(JE "$N/eng_lift_rc.csv"); e2=$(JE "$N/eng_missing.csv")
echo "NC7: judge engines 対照 rc=$e0 / lift_rc=1 に改変 rc=$e1 / 末尾行欠落 rc=$e2  (期待: 0 / 1 1)"
expect NC7-control "$e0" 0; expect NC7-broken "$e1 $e2" "1 1"

[ "$FAIL" = 0 ] && { echo "[sampler_nega] OK"; exit 0; }
echo "[sampler_nega] FAIL" >&2; exit 1
