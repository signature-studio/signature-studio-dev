#!/usr/bin/env bash
# kh_route_run.sh — kh_route.cjs (kh_route_build.sh の出力) を kh_gain の 61 シナリオで走らせ、native 出力と比較する (ICALL-17 #1025)。
#   前提: bash tools/icall/kh_route_build.sh が rc 0 / liftlib/work/kh_gain/diff/{scen.txt,out_native.txt} が存在 (liftlib の kh_gain 実行で生成)。
#   出力: work/kh_route/out_wasm.txt と比較サマリ (stdout)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T="$HERE/.."
W="$HERE/work/kh_route"
NAT="$T/liftlib/work/kh_gain/diff"
[ -f "$W/kh_route.cjs" ] || { echo "[kh_route_run] $W/kh_route.cjs が無い: kh_route_build.sh を先に実行" >&2; exit 2; }
[ -f "$NAT/out_native.txt" ] || { echo "[kh_route_run] $NAT/out_native.txt が無い: liftlib の kh_gain (native) 出力が必要" >&2; exit 2; }
ENTRY_VA=$((0x1804b0380 - 0x150000000))
python3 - "$T/liftlib/liftlib/harness/wasm_runner.mjs" "$W/wr_ott.mjs" "$ENTRY_VA" <<'EOF'
import sys
src, dst, va = sys.argv[1], sys.argv[2], int(sys.argv[3])
s = open(src).read()
a = "if (!M['_' + fname]) {"
b = "ret = M['_' + fname](...call);"
assert s.count(a) == 1 and s.count(b) == 1, "wasm_runner.mjs の形が変わった"
s = s.replace(a, "if (!M['_ott_run']) {")
s = s.replace(b, "ret = M['_ott_run'](%d, ...call, ...Array(8 - call.length).fill(0n));" % va)
x = "toString(16).padStart(16, '0')} ${'0'.padStart(16, '0')}`);"
assert s.count(x) == 1, "wasm_runner.mjs の R 行の形が変わった"
s = s.replace(x, "toString(16).padStart(16, '0')} ${(crashed ? 0n : BigInt.asUintN(64, M._ott_xmm0())).toString(16).padStart(16, '0')}`);")
open(dst, 'w').write(s)
EOF
cp "$NAT/scen.txt" "$W/scen.txt"
cp "$NAT/sig.json" "$W/sig.json"
(cd "$W" && timeout 900 node wr_ott.mjs kh_route.cjs function_1804b0380 sig.json scen.txt out_wasm.txt)
PYTHONPATH="$T/liftlib" python3 - "$NAT/out_native.txt" "$W/out_wasm.txt" <<'EOF'
import sys
from collections import Counter
from liftlib.harness.diff import parse_out
N = parse_out(sys.argv[1]); W = parse_out(sys.argv[2])
bit = 0; c = Counter(); trap = 0
for k in sorted(N):
    a, b = N[k], W.get(k)
    if b is None or b["crash"]:
        trap += 1; continue
    bad = [nm for nm in a["bufs"] if a["bufs"][nm][0] != b["bufs"].get(nm, ("", ""))[0]]
    if not bad: bit += 1
    for nm in bad: c[nm] += 1
print("scenarios=%d steps=%d bit_exact_steps=%d wasm_trap_steps=%d rax_match=%d" % (
    len(set(k[0] for k in N)), len(N), bit, trap, sum(1 for k in N if W.get(k) and N[k]["rax"] == W[k]["rax"])))
print("mismatch_buffers(step 数)=%s" % dict(c.most_common()))
EOF
