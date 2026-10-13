#!/usr/bin/env bash
# run_fa9.sh — FA-9: 制御層 setter 経路 (0x180c9d700 → 0x180ca1480 → 0x180da6c00) の実経路測定 + ネガティブコントロール。
#   (a) 観測プローブ (native_ctrl.c の FA_PROBE9=1): 0x180ca1480 の分岐 (C+0x2d0 vs C+0x328, key={1,0}) / map 検索結果 /
#       0x180da6c00 呼出回数 を epf 8 本 (S900..S907) で記録
#   (b) ネガコン1 FA_ALT9=1: C+0x328 を C+0x2d0 と不一致にし静的分岐を強制 → 後段が ERR になることを確認
#   (c) ネガコン2 摂動: epf の M+0x9dc4 (Mid Air) を 0.45→0.9 → 状態ダンプに届くか / L/R 出力が変わるか
#   (d) 既存 run_ctrl.sh 2 5 (native vs wasm bit-exact) を HEAD で再実行
# 判定: fa9_check.py の GATE 行 (FAIL なら非 0 で終了)。前提: build_ctrl.sh 済 (無ければ自動実行)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
[ -f "$CORE" ] || { echo "ERROR: $CORE が無い (素材 plugins-freshair を展開)"; exit 2; }
W="$HERE/work/ctrl"; [ -f "$W/iat_slots.txt" ] || bash "$HERE/build_ctrl.sh" >/dev/null || exit 2
cd "$W"; source "$HERE/env.sh"
python3 "$HERE/gen_ctrl_scen.py" ctrl_scen.txt 2 5 0xFA2C0001 >/dev/null || exit 2
head -8 ctrl_scen.txt > fa9_epf.txt
python3 "$HERE/fa9_check.py" mkpert fa9_epf.txt fa9_pert.txt || exit 2
clang -O1 -ffp-contract=off -frounding-math -w -o native_probe9 "$HERE/native/native_ctrl.c" || exit 2
FA_PROBE9=1 FA_HEAP_ZERO=1 ./native_probe9 "$CORE" fa9_epf.txt 0 > fa9_base.out 2> fa9_base.err
FA_ALT9=1 FA_PROBE9=1 FA_HEAP_ZERO=1 ./native_probe9 "$CORE" fa9_epf.txt 0 > fa9_alt.out 2> fa9_alt.err
FA_HEAP_ZERO=1 ./native_probe9 "$CORE" fa9_pert.txt 0 > fa9_pert.out 2>/dev/null
python3 "$HERE/fa9_check.py" check fa9_base.out fa9_base.err fa9_alt.out fa9_alt.err fa9_base.out fa9_pert.out
rc=$?
echo "--- run_ctrl (native vs wasm, HEAD) ---"
t0=$(date +%s); bash "$HERE/run_ctrl.sh" 2 5 | tail -1; ctrl_rc=${PIPESTATUS[0]}; t1=$(date +%s)
echo "run_ctrl rc=$ctrl_rc wall=$((t1 - t0))s"
[ $rc -eq 0 ] && [ "$ctrl_rc" -eq 0 ] || { echo "RESULT: FA-9 FAIL"; exit 1; }
echo "RESULT: FA-9 probe + negative controls PASS"
