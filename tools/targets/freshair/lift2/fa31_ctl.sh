#!/usr/bin/env bash
# fa31_ctl.sh — FA-31 (#2207): controller 木 (C+0x318 の [ctl+0xa8]) を埋める経路が harness の実行で通るかを数える (診断のみ・判定基準は持たない)。
#   base : 既定 (空 map)         node1: FA_NODE1=1 (手動で 1 node 注入)
#   陽性対照 ca7db0 (map lower_bound) は ca1480 の map 経路で呼ばれるはず (base 72 = ca1480 の呼出数)。
#   CAA31 行: 挿入候補 0x180caa820 (this=controller, [this+0xa8] を lookup して node を作る) の呼出後の木のノード数 (tree=)。
#   上流: e13590 (仮想 slot 2 of ModulationFormatter vt 0x181110fc8), e15030, e12f20, d8ae60, d8c4f0 の呼出回数。
# 前提: build_ctrl.sh 済 (work/ctrl)・素材 plugins-freshair を展開して fetch.sh 済 (work/win)。
# 出力: $OUT (既定 ${RUNNER_TEMP:-work}/fa31)。判定は出さず、各条件の summary 行を表示する。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
[ -f "$CORE" ] || { echo "ERROR: $CORE が無い (素材 plugins-freshair を展開して fetch.sh)"; exit 2; }
W="$HERE/work/ctrl"; [ -f "$W/ctrl_full.cjs" ] || bash "$HERE/build_ctrl.sh" >/dev/null || exit 2
OUT="${OUT:-${RUNNER_TEMP:-$HERE/work}/fa31}"; mkdir -p "$OUT"
cd "$W" || exit 2; source "$HERE/env.sh"
python3 "$HERE/gen_ctrl_scen.py" ctrl_scen.txt 2 5 0xFA2C0001 >/dev/null || exit 2
head -8 ctrl_scen.txt > fa31_epf.txt
clang -O1 -ffp-contract=off -frounding-math -w -o native_fa31 "$HERE/native/native_ctrl.c" || exit 2
run() {
  local name=$1; shift
  env FA_CTL31=1 FA_HEAP_ZERO=1 "$@" ./native_fa31 "$CORE" fa31_epf.txt 0 > "$OUT/$name.out" 2> "$OUT/$name.err"
  local rc=$?
  echo "$name rc=$rc $(grep '^CTL31 summary' "$OUT/$name.err")"
  echo "$name CAA31 行数: $(grep -c '^CAA31' "$OUT/$name.err") / tree 最大: $(grep -o 'tree=[0-9-]*' "$OUT/$name.err" | sort -t= -k2 -n | tail -1)"
}
run base
run node1 FA_NODE1=1
