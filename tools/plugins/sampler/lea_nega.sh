#!/usr/bin/env bash
# lea_e2e.sh (#627) の各検査の識別力を確認するネガティブコントロール。 対照 = 無改変で通ること、壊したものが落ちること。 exit 0 = 全て期待通り
#   NC1: closure_lea.py の BFS から entry を 1 つ落とす → L1 (total が indirect.json と一致) が FAIL (exit 1)
#   NC2: lea root を 1 つも足さない → L2 (lea 1 巡目が indirect.json の lea 残と一致) が FAIL
#   NC3: lea root を足すが call/jmp で広げない (固定点にしない) → L3 (固定点の独立検証) が FAIL
#   NC4: indirect.json の FL Keys lea_residual_funcs を +1 → L2 が FAIL
#   NC5: L5 の byte 走査閉包を空にする → L5 が FAIL
#   NC6: L6 (反例注入) で capstone 版にも byte 走査を使う (= 偽の到達先を区別できない検査器) → L6 が FAIL
#   NC7: L7 の命令境界判定を無効にし、閉包内の関数を指す E8/E9 も「偽の到達先」と数える (= 実在する call を偽と誤判定する census) → L7 が FAIL
#   NC8: judge.py shells に lea の status_run.csv の 1 行を壊した合成 CSV 6 種 (emcc_c_rc=1 / lift_rc=1 / lowering 後 f80=3 / 許容 0 の block に未実装 1 / 行欠落 / header のみ) → 全て非 0
#   NC9: lea_e2e.sh --skip-lift に emcc_c_rc=1 の行を足した status_run.csv を渡す → 非 0 かつ `[lea_e2e] OK` が出ない
#   NC10: indirect_defs.py (--lift-dir lea) に、FL Keys の final.ll から lea 由来の define を 1 つ消した lift-dir を渡す → 非 0
#   NC11: facts_total.py (FL Keys のみ) の base 段が closure_facts.py の facts.json と食い違う → F1 が FAIL
#   NC12: facts_total.py の線形走査を空にする → F3 が FAIL
#   NC13: facts_total.py の host 走査結果を空にする → F4 (計測不成立) が FAIL
# 事前: lea_e2e.sh 実行済み
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
N=work/sampler/lea_nega; rm -rf "$N"; mkdir -p "$N"
FAIL=0
expect() { if [ "$2" = "$3" ]; then echo "  ok  $1: $2"; else echo "  !! $1: 実測 $2 / 期待 $3" >&2; FAIL=1; fi; }
rc() { set +e; "$@" > "$N/last.out" 2>&1; local r=$?; set -e; echo $r; }
needfail() { grep -q "$1" "$N/last.out" || { echo "  !! $2: '$1' の FAIL 行が無い" >&2; FAIL=1; }; }

CL=sampler/closure_lea.py
T=sampler/_nc_closure_lea.py
FT=sampler/facts_total.py
T2=sampler/_nc_facts_total.py
SRC=work/sampler/lealift/status_run.csv
trap 'rm -f "$T" "$T2"; [ -f "$N/status_run.orig.csv" ] && cp "$N/status_run.orig.csv" "$SRC" || true' EXIT
# sed 置換が当たったことを確認する (当たっていないと対照と同じ入力で「FAIL しない」誤判定になる)
mutate() { # <src> <dst> <sed script> <label>
  sed "$3" "$1" > "$2"; cmp -s "$1" "$2" && { echo "  !! $4: sed が当たっていない" >&2; FAIL=1; } || true
}

cp "$CL" "$T"; expect "NC0 対照 closure_lea.py (無改変)" "$(rc python3 "$T" --out-dir "$N/out0")" 0

mutate "$CL" "$T" "s/entries = \[int(v, 16) - x.base for v in clo\[.entries.\].values()\]/entries = [int(v, 16) - x.base for v in clo['entries'].values()][1:]/" NC1
expect "NC1 entry を 1 つ落とす → L1 FAIL" "$(rc python3 "$T" --out-dir "$N/out1")" 1; needfail 'FAIL.*L1' NC1

mutate "$CL" "$T" "s/new = {f for f in leas if f in x.nonfw and f not in cur}/new = set()/" NC2
expect "NC2 lea root を足さない → L2 FAIL" "$(rc python3 "$T" --out-dir "$N/out2")" 1; needfail 'FAIL.*L2' NC2

mutate "$CL" "$T" "s/cur, front = x.bfs(sorted(cur) + sorted(new), calls)/cur, front = cur | new, front/" NC3
expect "NC3 lea root を call/jmp で広げない → L3 FAIL" "$(rc python3 "$T" --out-dir "$N/out3")" 1; needfail 'FAIL.*L3' NC3

python3 - <<'PY'
import json
j = json.load(open('work/sampler/indirect.json')); j['FL Keys']['lea_residual_funcs'] += 1
json.dump(j, open('work/sampler/lea_nega/indirect_bad.json', 'w'))
PY
expect "NC4 indirect.json の lea_residual_funcs +1 → L2 FAIL" "$(rc python3 "$CL" --out-dir "$N/out4" --indirect-json "$N/indirect_bad.json")" 1; needfail 'FAIL.*L2' NC4

mutate "$CL" "$T" "s/over, _ = x.bfs(sorted(base | roots | lea_all), x.edges_bytescan)/over, _ = x.bfs([], x.edges_bytescan)/" NC5
expect "NC5 byte 走査閉包を空にする → L5 FAIL" "$(rc python3 "$T" --out-dir "$N/out5")" 1; needfail 'FAIL.*L5' NC5

mutate "$CL" "$T" "s/cap = x.edges(f0)\[0\]/cap = x.edges_bytescan(f0)/" NC6
expect "NC6 反例注入の capstone 側を byte 走査にする → L6 FAIL" "$(rc python3 "$T" --out-dir "$N/out6")" 1; needfail 'FAIL.*L6' NC6

mutate "$CL" "$T" "s/or o in starts:/or False:/; s/if t in x.nonfw and t not in total2:/if t in x.nonfw:/" NC7
grep -q "or False:" "$T" && grep -q "if t in x.nonfw:" "$T" || { echo "  !! NC7: sed が 2 箇所とも当たっていない" >&2; FAIL=1; }
expect "NC7 census の境界判定を無効化し、閉包内の関数も偽到達先と数える → L7 FAIL" "$(rc python3 "$T" --out-dir "$N/out7")" 1; needfail 'FAIL.*L7' NC7
rm -f "$T"

# NC8: judge.py shells に壊した合成 CSV
BL="$(python3 sampler/targets.py blocks | tr ' ' ',')"
ALLOW="$(python3 sampler/targets.py allow-unimpl)"
NAMES="$(python3 -c 'import sys; sys.path.insert(0, "sampler"); import targets; print(",".join(targets.ALLOW_UNIMPL_NAMES))')"
J() { rc python3 sampler/judge.py shells "$1" --blocks "$BL" --allow-unimpl "$ALLOW" --allow-names "$NAMES"; }
expect "NC8 対照 (無改変 status_run.csv)" "$(J "$SRC")" 0
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
mut 22386 emcc_c_rc 1;       expect "NC8a emcc_c_rc=1" "$(J "$N/mut.csv")" 1
mut 23617 lift_rc 1;         expect "NC8b lift_rc=1" "$(J "$N/mut.csv")" 1
mut 23658 f80_funcs 3;       expect "NC8c lowering 後 f80=3 (Granulizer)" "$(J "$N/mut.csv")" 1
mut 24175 declares_unimpl 1; expect "NC8d 許容 0 の block に未実装 1" "$(J "$N/mut.csv")" 1
mut 23663 - -;               expect "NC8e 行欠落" "$(J "$N/mut.csv")" 1
mut - - -;                   expect "NC8f header のみ" "$(J "$N/mut.csv")" 1

# NC9: e2e 本体 (--skip-lift) に不合格行を足した status_run.csv
cp "$SRC" "$N/status_run.orig.csv"
r9a=$(rc bash sampler/lea_e2e.sh --skip-lift); expect "NC9 対照 (--skip-lift 無改変)" "$r9a" 0
grep -q '\[lea_e2e\] OK' "$N/last.out" || { echo "  !! NC9: 対照に OK 行が無い" >&2; FAIL=1; }
python3 - "$SRC" <<'PY'
import csv, sys
p = sys.argv[1]
rows = list(csv.reader(open(p))); hdr = rows[0]
r = list(rows[1]); r[hdr.index('emcc_c_rc')] = '1'
csv.writer(open(p, 'w')).writerows(rows + [r])
PY
r9b=$(rc bash sampler/lea_e2e.sh --skip-lift); expect "NC9 emcc_c_rc=1 の行を追記 → 非 0" "$([ "$r9b" != 0 ] && echo nonzero)" nonzero
if grep -q '\[lea_e2e\] OK' "$N/last.out"; then echo "  !! NC9: 不合格なのに OK 行が出た" >&2; FAIL=1; fi
cp "$N/status_run.orig.csv" "$SRC"

# NC10: indirect_defs.py (lea の ranges) に、FL Keys の final.ll から lea 由来の define を 1 つ消した lift-dir を渡す
B=22386
expect "NC10 対照 (indirect_defs --lift-dir lea 無改変)" "$(rc python3 sampler/indirect_defs.py --lift-dir work/sampler/lealift --ranges-dir work/sampler/lea)" 0
LEAFN=$(python3 - <<'PY'
import json
# total2 − total の先頭 1 関数 (lea 由来) の開始 VA
a = set(int(r.split('-')[0], 16) for r in open('work/sampler/lea/block22386.ranges.txt').read().split(','))
b = set(int(r.split('-')[0], 16) for r in open('work/sampler/lea/block22386.total.ranges.txt').read().split(','))
print('%x' % sorted(a - b)[0])
PY
)
mkdir -p "$N/nc10/$B"
python3 - "work/sampler/lealift/$B/p.final.ll" "$N/nc10/$B/p.final.ll" "$LEAFN" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
m = re.search(r'^define [^\n]*@function_%s\(.*?^}\n' % sys.argv[3], s, re.M | re.S)
assert m, 'define が見つからない'
open(sys.argv[2], 'w').write(s[:m.start()] + s[m.end():])
PY
for b in 23617 23658 23662 23663 24172 24175; do mkdir -p "$N/nc10/$b"; cp work/sampler/lealift/$b/p.final.ll "$N/nc10/$b/p.final.ll"; done
expect "NC10 lea 由来 function_$LEAFN の define を消す → 非 0" "$(rc python3 sampler/indirect_defs.py --lift-dir "$N/nc10" --ranges-dir work/sampler/lea)" 1
grep -q "欠落 1 .*FAIL" "$N/last.out" || { echo "  !! NC10: 欠落 1 の FAIL 行が無い" >&2; FAIL=1; }

# NC11-13: facts_total.py (FL Keys のみ。 走査 1 回 = 数十秒)
expect "NC11 対照 (facts_total --only 'FL Keys' 無改変)" "$(rc python3 "$FT" --only 'FL Keys' --out "$N/ft0.json")" 0
python3 - <<'PY'
import json
j = json.load(open('work/sampler/facts.json')); j['FL Keys']['host']['ids']['2'] += 1
json.dump(j, open('work/sampler/lea_nega/facts_bad.json', 'w'))
PY
expect "NC11 base 段の facts.json を +1 → F1 FAIL" "$(rc python3 "$FT" --only 'FL Keys' --out "$N/ft1.json" --facts "$N/facts_bad.json")" 1; needfail 'FAIL.*F1' NC11

mutate "$FT" "$T2" "s/^        lin = linear_ids(.*\$/        lin = collections.Counter()/" NC12
expect "NC12 線形走査を空にする → F3 FAIL" "$(rc python3 "$T2" --only 'FL Keys' --out "$N/ft2.json")" 1; needfail 'FAIL.*F3' NC12

mutate "$FT" "$T2" "s/^        _, res = host_calls.scan(fn)\$/        res = []/" NC13
expect "NC13 host 走査結果を空にする → F4 FAIL" "$(rc python3 "$T2" --only 'FL Keys' --out "$N/ft3.json")" 1; needfail 'FAIL.*F4' NC13

[ "$FAIL" = 0 ] && echo "[lea_nega] OK: 全ネガコンが期待通り" || { echo "[lea_nega] FAIL" >&2; exit 1; }
