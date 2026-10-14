#!/usr/bin/env bash
# fa32_node1.sh — FA-32 (#2306): FA_NODE1=1 の setter ERR 8 行の原因切り分け (診断のみ・判定基準は持たない)。
#   R1: FA_NODE1 (probe 無し)         R2: R1 + FA_ALT9 (静的分岐の negative control)
#   P : FA_PROBE9 + FA_NODE1 (guard 無し / FA_P9GUARD 有り)
#   G1: FA_NODE1_ZBIG (Z=0x2400 zero)  G5: FA_NODE1_ZOBJ (Z+0x2c0 に vtable 付き偽オブジェクト)
#   C : FA_PROBE9 + FA_CHAIN9 + FA_OUT0 (2 回目の ca1480 の C と out[0] を同一行で照合: C==Z, out0==C+0x2b0)
# 前提: build_ctrl.sh 済 (work/ctrl)・素材 plugins-freshair を展開して fetch.sh 済 (work/win)。
# 出力: $OUT (既定 ${RUNNER_TEMP:-work}/fa32)。判定は出さず、各条件の ERR 件数と先頭 ERR・照合結果を表示する。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
[ -f "$CORE" ] || { echo "ERROR: $CORE が無い (素材 plugins-freshair を展開して fetch.sh)"; exit 2; }
W="$HERE/work/ctrl"; [ -f "$W/ctrl_full.cjs" ] || bash "$HERE/build_ctrl.sh" >/dev/null || exit 2
OUT="${OUT:-${RUNNER_TEMP:-$HERE/work}/fa32}"; mkdir -p "$OUT"
cd "$W" || exit 2; source "$HERE/env.sh"
python3 "$HERE/gen_ctrl_scen.py" ctrl_scen.txt 2 5 0xFA2C0001 >/dev/null || exit 2
head -8 ctrl_scen.txt > fa32_epf.txt
clang -O1 -ffp-contract=off -frounding-math -w -o native_fa32 "$HERE/native/native_ctrl.c" || exit 2
run() {
  local name=$1; shift
  env FA_DBG=1 FA_HEAP_ZERO=1 "$@" ./native_fa32 "$CORE" fa32_epf.txt 0 > "$OUT/$name.out" 2> "$OUT/$name.err"
  local rc=$? n; n=$(grep -c '^ERR' "$OUT/$name.err")
  echo "$name rc=$rc ERR=$n/8 first: $(grep -m1 '^ERR' "$OUT/$name.err" | sed -E 's/^ERR (S[0-9]+) sig=([0-9]+) rip=([0-9a-f]+) addr=([0-9a-f]+).* rcx=([0-9a-f]+).*/\1 sig=\2 rip=\3 addr=\4 rcx=\5/')"
}
run R1 FA_NODE1=1
run R2 FA_NODE1=1 FA_ALT9=1
run P_noguard FA_NODE1=1 FA_PROBE9=1
run P_guard FA_NODE1=1 FA_PROBE9=1 FA_P9GUARD=1
run G1 FA_NODE1=1 FA_NODE1_ZBIG=1
run G5 FA_NODE1=1 FA_NODE1_ZOBJ=1
run C FA_NODE1=1 FA_PROBE9=1 FA_CHAIN9=1 FA_OUT0=1
python3 - "$OUT/C.err" <<'EOF'
import re, sys
Z = None; rows = []
for ln in open(sys.argv[1]):
    m = re.match(r'NODEZ Z=(0x[0-9a-f]+)', ln)
    if m: Z = int(m.group(1), 16); continue
    m = re.match(r'CHAIN9 (S\d+) depth=\d+ C=(0x[0-9a-f]+) key=\S+ kc=(\d+) k0=(\d+) out0=([0-9a-f]+)', ln)
    if m and m.group(3) == '0' and m.group(4) == '1':   # 2 回目 (key 個数 0 → key 無し分岐)
        C = int(m.group(2), 16); o0 = int(m.group(5), 16); rows.append((C == Z, o0 - C == 0x2b0))
print(f"C: 2nd-call rows={len(rows)} C==Z {sum(r[0] for r in rows)}/{len(rows)} out0==C+0x2b0 {sum(r[1] for r in rows)}/{len(rows)}")
EOF
