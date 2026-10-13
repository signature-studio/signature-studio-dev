#!/usr/bin/env bash
# unr_e2e.sh (#667) の各検査の識別力を確認するネガティブコントロール。 対照 = 無改変で期待どおり、壊したものが期待どおり落ちること。 exit 0 = 全て期待通り
#   NC0: 対照 closure_unreached.py (無改変) → rc 0
#   NC1: BFS の seed から (a) RVA32 の根を外す → U2 (根 ⊆ total3) が FAIL
#   NC2: 未検証 (受入から除外)。 BFS の辺から命令内即値を外す → U2 FAIL を期待するが、即値辺は実データで 0 件のため識別できない (REPORT_UNREACHED §2d-7)。 即値の検出経路は NC7 で確認
#   NC3: 排他分類の (c) に (a)(b) の関数を二重計上する → U4 (排他合計) が FAIL
#   NC4: capstone 側の RVA32 集合に偽の値を注入する → U1 (byte 走査の部分集合) が FAIL
#   NC5: judge.py shells の入力 CSV の 1 行に emcc_c_rc=1 → judge が FAIL (rc 1)
#   NC6: 対照 = 無改変の unr_e2e.sh --skip-lift は、既知の range 欠落 (AC2 未達) だけで rc 1 (judge は PASS・indirect_defs は FAIL・OK 無し)。 同 + emcc_c_rc=1 の行を追記 → judge が FAIL に変わり rc ≠ 0・OK 無し
#   NC7: 合成 bytes (mov rax, imm64 = 開始 VA) を imm_capstone が検出する。 開始 VA が無ければ検出しない (即値の検出経路の動作確認)
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
echo "  -- NC2 未検証: 即値辺は実データで 0 件のため、外しても結果は変わらない (受入から除外。 即値の検出経路は NC7)"

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

# NC6: e2e 本体 (--skip-lift). 対照は既知の不合格 (range 欠落) だけで rc 1 になることを確認する
cp "$SRC" "$N/status_run.orig.csv"
r6a=$(rc bash sampler/unr_e2e.sh --skip-lift); expect "NC6 対照 (無改変 --skip-lift): 既知の range 欠落のみで rc 1" "$r6a" 1
grep -q 'judge shells: PASS 7/7' "$N/last.out" || { echo "  !! NC6 対照: judge が PASS していない" >&2; FAIL=1; }
grep -q 'indirect_defs: FAIL' "$N/last.out" || { echo "  !! NC6 対照: indirect_defs の FAIL が無い (既知の欠落が出ていない)" >&2; FAIL=1; }
if grep -q '\[unr_e2e\] OK' "$N/last.out"; then echo "  !! NC6 対照: 既知の不合格なのに OK 行が出た" >&2; FAIL=1; fi
python3 - "$SRC" <<'PY'
import csv, sys
p = sys.argv[1]
rows = list(csv.reader(open(p))); hdr = rows[0]
r = list(rows[1]); r[hdr.index('emcc_c_rc')] = '1'
csv.writer(open(p, 'w')).writerows(rows + [r])
PY
r6b=$(rc bash sampler/unr_e2e.sh --skip-lift); expect "NC6 emcc_c_rc=1 の行を追記 → 非 0" "$([ "$r6b" != 0 ] && echo nonzero)" nonzero
grep -q 'judge shells: FAIL' "$N/last.out" || { echo "  !! NC6: 追記で judge が FAIL しなかった" >&2; FAIL=1; }
if grep -q '\[unr_e2e\] OK' "$N/last.out"; then echo "  !! NC6: 不合格なのに OK 行が出た" >&2; FAIL=1; fi
cp "$N/status_run.orig.csv" "$SRC"

# NC7: 合成 bytes で即値の検出経路 (imm_capstone) を確認する。 mov rax, imm64 (= 開始 VA) は検出、開始 VA が無ければ非検出
cat > "$N/nc7.py" <<'PY'
import sys
sys.path.insert(0, 'sampler')
import capstone
import closure_unreached as CU
class X: pass
x = X(); x.base = 0x140000000
x.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); x.md.detail = True
body = b'\x48\xb8' + (x.base + 0x2000).to_bytes(8, 'little') + b'\xc3'
x.body = lambda f: body
pos = CU.imm_capstone(x, 0x1000, {0x2000})
neg = CU.imm_capstone(x, 0x1000, {0x3000})
sys.exit(0 if pos == ({0x2000}, set()) and neg == (set(), set()) else 1)
PY
expect "NC7 合成 mov rax,imm64 の即値 (開始 VA あり → 検出 / なし → 非検出)" "$(rc python3 "$N/nc7.py")" 0

[ "$FAIL" = 0 ] && echo "[unr_nega] OK: 全ネガコンが期待通り (NC2 は未検証として除外)" || { echo "[unr_nega] FAIL" >&2; exit 1; }
