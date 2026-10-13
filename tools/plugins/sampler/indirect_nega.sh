#!/usr/bin/env bash
# indirect_e2e.sh (#537) の各検査の識別力を確認するネガティブコントロール。 対照 = 無改変で通ること、壊したものが落ちること。 exit 0 = 全て期待通り
#   NC1: closure_indirect.py の BFS から「元の閉包 entry を 1 つ落とす」→ C1 (base 再現) が FAIL (exit 1)
#   NC2: root 判定を壊す (データ参照 qword の集合を空にする) → C2 (unreached.json と一致) が FAIL (exit 1)
#   NC3: unreached.json の dataref_funcs を +1 → C2 が FAIL (exit 1)
#   NC4: 推移閉包の ranges 末尾 1 range を落として FL Keys を再 lift → 落とした関数が final.ll から消える (1 → 0)
#   NC5: judge.py shells に indirect の status_run.csv の 1 行を壊した合成 CSV 6 種 (emcc_c_rc=1 / lift_rc=1 / f80=3 / 未実装 1 を許容 0 の block / 行欠落 / header のみ) → 全て非 0
#   NC6: indirect_e2e.sh --skip-lift に emcc_c_rc=1 の行を足した status_run.csv を渡す → 非 0 かつ `[indirect_e2e] OK` が出ない
#   NC7: indirect_defs.py に FL Keys の final.ll から define を 1 つ消した lift-dir を渡す → 非 0 (range 単位の欠落検出)
# 事前: indirect_e2e.sh 実行済み
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
N=work/sampler/indirect_nega; rm -rf "$N"; mkdir -p "$N"
FAIL=0
expect() { if [ "$2" = "$3" ]; then echo "  ok  $1: $2"; else echo "  !! $1: 実測 $2 / 期待 $3" >&2; FAIL=1; fi; }
rc() { set +e; "$@" > "$N/last.out" 2>&1; local r=$?; set -e; echo $r; }

# NC1-NC3: closure_indirect.py のコピーを壊す (HERE 基準の相対参照を保つため同じ dir に置く)
CI=sampler/closure_indirect.py
T=sampler/_nc_closure_indirect.py
trap 'rm -f "$T"' EXIT
cp "$CI" "$T"; r0=$(rc python3 "$T" --out-dir "$N/out0"); expect "NC0 対照 (無改変)" "$r0" 0
sed 's/entries = \[int(v, 16) - x.base for v in clo\[.entries.\].values()\]/entries = [int(v, 16) - x.base for v in clo["entries"].values()][1:]/' "$CI" > "$T"
cmp -s "$CI" "$T" && { echo "  !! NC1: sed が当たっていない" >&2; FAIL=1; }
r1=$(rc python3 "$T" --out-dir "$N/out1"); expect "NC1 entry を 1 つ落とす → C1 FAIL" "$r1" 1
grep -q 'FAIL.*C1 base 再現' "$N/last.out" || { echo "  !! NC1: C1 の FAIL 行が無い" >&2; FAIL=1; }

sed 's/roots = x.dataref()(cand) if cand else set()/roots = set()/' "$CI" > "$T"
cmp -s "$CI" "$T" && { echo "  !! NC2: sed が当たっていない" >&2; FAIL=1; }
r2=$(rc python3 "$T" --out-dir "$N/out2"); expect "NC2 root を空にする → C2 FAIL" "$r2" 1
grep -q 'FAIL.*C2 root' "$N/last.out" || { echo "  !! NC2: C2 の FAIL 行が無い" >&2; FAIL=1; }

cp "$CI" "$T"
python3 - <<'PY'
import json
p = 'work/sampler/unreached.json'
j = json.load(open(p)); j['FL Keys']['dataref_funcs'] += 1
json.dump(j, open('work/sampler/indirect_nega/unreached_bad.json', 'w'))
PY
sed "s#os.path.join(WORK, 'sampler', 'unreached.json')#'$N/unreached_bad.json'#" "$CI" > "$T"
cmp -s "$CI" "$T" && { echo "  !! NC3: sed が当たっていない" >&2; FAIL=1; }
r3=$(rc python3 "$T" --out-dir "$N/out3"); expect "NC3 unreached.json の dataref_funcs +1 → C2 FAIL" "$r3" 1
rm -f "$T"

# NC4: 推移閉包の ranges 末尾 1 つを落として FL Keys (最小) を再 lift
B=22386
R=work/sampler/indirect/block$(printf %05d $B).ranges.txt
n=$(tr ',' '\n' < "$R" | wc -l)
LAST=$(tr ',' '\n' < "$R" | tail -n 1 | cut -d- -f1 | sed 's/^0x//')
d0=$(grep -c '^define' work/sampler/indirectlift/$B/p.final.ll); h0=$(grep -c "^define .*@function_$LAST\\b" work/sampler/indirectlift/$B/p.final.ll || true)
tr ',' '\n' < "$R" | head -n $((n - 1)) | paste -sd, > "$N/ranges_minus1.txt"
bash sampler/lift_from_ll.sh "$FL_WIN64_DIR/extracted/block$(printf %05d $B)_PE.bin" "$N/ranges_minus1.txt" "$N/lift" p 600 > "$N/lift.log" 2>&1
d1=$(grep -c '^define' "$N/lift/p.final.ll"); h1=$(grep -c "^define .*@function_$LAST\\b" "$N/lift/p.final.ll" || true)
echo "NC4: ranges $n -> $((n - 1)), 落とした関数 function_$LAST: control define=$d0 present=$h0 / minus1 define=$d1 present=$h1"
expect "NC4 present (対照 / 欠落)" "$h0 $h1" "1 0"
{ [ "$d1" -lt "$d0" ] && [ "$d1" -gt 0 ]; } || { echo "  !! NC4: define 数 $d0 -> $d1" >&2; FAIL=1; }

# NC5: judge.py shells に壊した合成 CSV
BL="$(python3 sampler/targets.py blocks | tr ' ' ',')"
ALLOW="$(python3 sampler/targets.py allow-unimpl)"
NAMES="$(python3 -c 'import sys; sys.path.insert(0, "sampler"); import targets; print(",".join(targets.ALLOW_UNIMPL_NAMES))')"
SRC=work/sampler/indirectlift/status_run.csv
J() { rc python3 sampler/judge.py shells "$1" --blocks "$BL" --allow-unimpl "$ALLOW" --allow-names "$NAMES"; }
expect "NC5 対照 (無改変 status_run.csv)" "$(J "$SRC")" 0
mut() { python3 - "$SRC" "$N/mut.csv" "$1" "$2" "$3" <<'PY'
import csv, sys
src, out, blk, col, val = sys.argv[1:]
rows = list(csv.reader(open(src))); hdr, body = rows[0], rows[1:]
if col == '-' and blk == '-': body = []
elif col == '-': body = [r for r in body if r[0] != blk]
else:
    for r in body:
        if r[0] == blk: r[hdr.index(col)] = val
csv.writer(open(out, 'w')).writerows([hdr] + body)
PY
}
mut 22386 emcc_c_rc 1;      expect "NC5a emcc_c_rc=1" "$(J "$N/mut.csv")" 1
mut 23617 lift_rc 1;        expect "NC5b lift_rc=1" "$(J "$N/mut.csv")" 1
mut 24172 f80_funcs 3;      expect "NC5c f80=3" "$(J "$N/mut.csv")" 1
mut 24175 declares_unimpl 1; expect "NC5d 許容 0 の block に未実装 1" "$(J "$N/mut.csv")" 1
mut 23663 - -;              expect "NC5e 行欠落" "$(J "$N/mut.csv")" 1
mut - - -;                  expect "NC5f header のみ" "$(J "$N/mut.csv")" 1

# NC6: e2e 本体 (--skip-lift) に不合格行を足した status_run.csv
cp "$SRC" "$N/status_run.orig.csv"
trap 'cp "$N/status_run.orig.csv" "$SRC" 2>/dev/null || true; rm -f "$T"' EXIT
r6a=$(rc bash sampler/indirect_e2e.sh --skip-lift); expect "NC6 対照 (--skip-lift 無改変)" "$r6a" 0
grep -q '\[indirect_e2e\] OK' "$N/last.out" || { echo "  !! NC6: 対照に OK 行が無い" >&2; FAIL=1; }
python3 - "$SRC" <<'PY'
import csv, sys
p = sys.argv[1]
rows = list(csv.reader(open(p))); hdr = rows[0]
r = list(rows[1]); r[hdr.index('emcc_c_rc')] = '1'
csv.writer(open(p, 'w')).writerows(rows + [r])
PY
r6b=$(rc bash sampler/indirect_e2e.sh --skip-lift); expect "NC6 emcc_c_rc=1 の行を追記 → 非 0" "$([ "$r6b" != 0 ] && echo nonzero)" nonzero
if grep -q '\[indirect_e2e\] OK' "$N/last.out"; then echo "  !! NC6: 不合格なのに OK 行が出た" >&2; FAIL=1; fi
cp "$N/status_run.orig.csv" "$SRC"

# NC7: indirect_defs.py に、FL Keys の final.ll から define を 1 つ消した lift-dir を渡す → 非 0 (対照 rc 0)
expect "NC7 対照 (indirect_defs 無改変)" "$(rc python3 sampler/indirect_defs.py)" 0
mkdir -p "$N/nc7/$B"
python3 - "work/sampler/indirectlift/$B/p.final.ll" "$N/nc7/$B/p.final.ll" "$LAST" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
m = re.search(r'^define [^\n]*@function_%s\(.*?^}\n' % sys.argv[3], s, re.M | re.S)
assert m, 'define が見つからない'
open(sys.argv[2], 'w').write(s[:m.start()] + s[m.end():])
PY
for b in 23617 23658 23662 23663 24172 24175; do mkdir -p "$N/nc7/$b"; cp work/sampler/indirectlift/$b/p.final.ll "$N/nc7/$b/p.final.ll"; done
expect "NC7 define を 1 つ消す → 非 0" "$(rc python3 sampler/indirect_defs.py --lift-dir "$N/nc7")" 1
grep -q "欠落 1 .*FAIL" "$N/last.out" || { echo "  !! NC7: 欠落 1 の FAIL 行が無い" >&2; FAIL=1; }

[ "$FAIL" = 0 ] && echo "[indirect_nega] OK: 全ネガコンが期待通り" || { echo "[indirect_nega] FAIL" >&2; exit 1; }
