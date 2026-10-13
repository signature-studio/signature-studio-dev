#!/usr/bin/env bash
# unr_e2e.sh (#667) の各検査の識別力を確認するネガティブコントロール。 対照 = 無改変で通ること、壊したものが落ちること。 exit 0 = 全て期待通り
#   NC0: 対照 closure_unreached.py (無改変) → rc 0
#   NC1: BFS の seed から (a) RVA32 の根を外す → U2 (根 ⊆ total3) が FAIL
#   NC2: BFS の辺から命令内即値を外す → U6 (即値辺の識別力・合成入力) が FAIL (実データの即値辺は 0 件のため合成入力で示す)
#   NC2 (別案): 即値辺を持つ合成入力 (nc2_imm_synth.py) で、BFS の辺から命令内即値を外すと U2 が FAIL (対照は PASS) (#879)
#   NC3: 排他分類の (c) に (a)(b) の関数を二重計上する → U4 (排他合計) が FAIL
#   NC4: capstone 側の RVA32 集合に偽の値を注入する → U1 (byte 走査の部分集合) が FAIL
#   NC5: judge.py shells の入力 CSV の 1 行に emcc_c_rc=1 → judge が FAIL (rc 1)
#   NC6: unr_e2e.sh --skip-lift に emcc_c_rc=1 の行を追記 → 非 0 かつ `[unr_e2e] OK` が出ない
#   NC7: export 名の改名 (export_rename.py) を外した lift 出力 → indirect_defs (range 欠落監査) が FAIL
# 事前: unr_e2e.sh 実行済み (work/sampler/unrlift/status_run.csv と work/sampler/unr/ がある)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
N=work/sampler/unr_nega; rm -rf "$N"; mkdir -p "$N"
FAIL=0
expect() { if [ "$2" = "$3" ]; then echo "  ok  $1: $2"; else echo "  !! $1: 実測 $2 / 期待 $3" >&2; FAIL=1; fi; }
rc() { set +e; "$@" > "$N/last.out" 2>&1; local r=$?; set -e; echo $r; }
needfail() { grep -q "$1" "$N/last.out" || { echo "  !! $2: '$1' の FAIL 行が無い" >&2; FAIL=1; }; }

CL=sampler/closure_unreached.py
T=sampler/_nc_closure_unreached.py
SRC=work/sampler/unrlift/status_run.csv
trap 'rm -f "$T"; [ -f "$N/status_run.orig.csv" ] && cp "$N/status_run.orig.csv" "$SRC" || true' EXIT
# sed 置換が当たったことを確認する (当たっていないと対照と同じ入力で「FAIL しない」誤判定になる)
mutate() { # <src> <dst> <sed script> <label>
  sed "$3" "$1" > "$2"; cmp -s "$1" "$2" && { echo "  !! $4: sed が当たっていない" >&2; FAIL=1; } || true
}

cp "$CL" "$T"; expect "NC0 対照 closure_unreached.py (無改変)" "$(rc python3 "$T" --out-dir "$N/out0")" 0

mutate "$CL" "$T" "s/total3, _ = x.bfs(sorted(total2 | roots), edge3)/total3, _ = x.bfs(sorted(total2 | B_live), edge3)/" NC1
expect "NC1 根から (a) RVA32 を外す → U2 FAIL" "$(rc python3 "$T" --out-dir "$N/out1")" 1; needfail 'FAIL.*U2' NC1

mutate "$CL" "$T" "s/^        return x.edges(f)\[0\] | x.edges(f)\[1\] | i\[0\] | i\[1\]\$/        return x.edges(f)[0] | x.edges(f)[1]/" NC2
expect "NC2 BFS の辺から命令内即値を外す → U6 FAIL (合成入力で即値辺の識別力を示す)" "$(rc python3 "$T" --out-dir "$N/out2")" 1; needfail 'FAIL.*U6' NC2
# NC2: 即値辺を外す検査の識別力は、実データ (即値辺 0 件) では示せないため、即値辺を持つ合成入力で示す (#879)
expect "NC2a 合成入力・即値辺あり (対照) → U2 PASS" "$(rc python3 sampler/nc2_imm_synth.py)" 0
expect "NC2b 合成入力・BFS から即値辺を外す → U2 FAIL" "$(rc python3 sampler/nc2_imm_synth.py --drop-imm-bfs)" 1; needfail 'FAIL.*U2' NC2b

mutate "$CL" "$T" "s/        ex_c = C - A - B_all\$/        ex_c = C - B_all/" NC3
expect "NC3 (c) に (a) を二重計上 → U4 FAIL" "$(rc python3 "$T" --out-dir "$N/out3")" 1; needfail 'FAIL.*U4' NC3

mutate "$CL" "$T" "s/A_cap = set().union(/A_cap = {0x7fffff01} | set().union(/" NC4
expect "NC4 capstone 側に偽の RVA32 を注入 → U1 FAIL" "$(rc python3 "$T" --out-dir "$N/out4")" 1; needfail 'FAIL.*U1' NC4
rm -f "$T"

# NC5: judge.py shells に 1 行だけ emcc_c_rc=1 の合成 CSV
BL="$(python3 sampler/targets.py blocks | tr ' ' ',')"
ALLOW="$(python3 sampler/targets.py allow-unimpl)"
NAMES="$(python3 -c 'import sys; sys.path.insert(0, "sampler"); import targets; print(",".join(targets.ALLOW_UNIMPL_NAMES))')"
J() { rc python3 sampler/judge.py shells "$1" --blocks "$BL" --allow-unimpl "$ALLOW" --allow-names "$NAMES"; }
expect "NC5 対照 (無改変 status_run.csv)" "$(J "$SRC")" 0
python3 - "$SRC" "$N/mut.csv" <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1]))); hdr = rows[0]
for r in rows[1:]:
    if r[0] == '22386':
        r[hdr.index('emcc_c_rc')] = '1'
csv.writer(open(sys.argv[2], 'w')).writerows(rows)
PY
expect "NC5 emcc_c_rc=1 の 1 行 → judge FAIL" "$(J "$N/mut.csv")" 1

# NC6: e2e 本体 (--skip-lift) に不合格行を追記
cp "$SRC" "$N/status_run.orig.csv"
r6a=$(rc bash sampler/unr_e2e.sh --skip-lift); expect "NC6 対照 (--skip-lift 無改変)" "$r6a" 0
grep -q '\[unr_e2e\] OK' "$N/last.out" || { echo "  !! NC6: 対照に OK 行が無い" >&2; FAIL=1; }
python3 - "$SRC" <<'PY'
import csv, sys
p = sys.argv[1]
rows = list(csv.reader(open(p))); hdr = rows[0]
r = list(rows[1]); r[hdr.index('emcc_c_rc')] = '1'
csv.writer(open(p, 'w')).writerows(rows + [r])
PY
r6b=$(rc bash sampler/unr_e2e.sh --skip-lift); expect "NC6 emcc_c_rc=1 の行を追記 → 非 0" "$([ "$r6b" != 0 ] && echo nonzero)" nonzero
if grep -q '\[unr_e2e\] OK' "$N/last.out"; then echo "  !! NC6: 不合格なのに OK 行が出た" >&2; FAIL=1; fi
cp "$N/status_run.orig.csv" "$SRC"

# NC7: export 名の改名 (export_rename.py) を外した出力 (p.prerename.ll) → range 欠落監査が FAIL する
rm -rf "$N/nc7"; mkdir -p "$N/nc7"
for d in work/sampler/unrlift/*/; do
  b="$(basename "$d")"; mkdir -p "$N/nc7/$b"; cp "$d/p.prerename.ll" "$N/nc7/$b/p.final.ll"
done
expect "NC7 改名前 (export 名のまま) → indirect_defs FAIL" "$(rc python3 sampler/indirect_defs.py --lift-dir "$N/nc7" --ranges-dir work/sampler/unr)" 1; needfail 'FAIL' NC7

# NC8: 改名先 function_<VA> が既に出力中 (衝突) → export_rename.py が非 0 で終わる (unr_lift.sh はこの rc を lift_rc に反映する)
rm -rf "$N/nc8"; mkdir -p "$N/nc8"
read -r NC8_B NC8_LL NC8_NEW <<< "$(python3 - "$N/nc8" <<'PY'
import glob, json, os, shutil, sys
out = sys.argv[1]
for d in sorted(glob.glob('work/sampler/unrlift/*/')):
    rep = os.path.join(d, 'export_rename.json')
    if not os.path.exists(rep) or not json.load(open(rep)):
        continue
    b = os.path.basename(os.path.normpath(d)); v = next(iter(json.load(open(rep)).values()))
    ll = os.path.join(out, 'p.ll'); shutil.copy(os.path.join(d, 'p.prerename.ll'), ll)
    open(ll, 'a').write('\ndefine void @%s() {\n  ret void\n}\n' % v['new'])
    print(b, ll, v['new']); break
PY
)"
[ -n "${NC8_B:-}" ] || { echo "  !! NC8: 改名された関数が無い" >&2; FAIL=1; }
NC8_PE="$FL_WIN64_DIR/extracted/block$(printf %05d "${NC8_B:-0}")_PE.bin"
NC8_R="work/sampler/unr/block$(printf %05d "${NC8_B:-0}").ranges.txt"
expect "NC8 改名先が既に存在 (衝突) → export_rename.py 非 0" "$(rc python3 sampler/export_rename.py "$NC8_LL" "$NC8_PE" "$NC8_R")" 1

[ "$FAIL" = 0 ] && echo "[unr_nega] OK: 全ネガコンが期待通り" || { echo "[unr_nega] FAIL" >&2; exit 1; }
