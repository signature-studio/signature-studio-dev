#!/usr/bin/env bash
# prod_order_942.sh — #942: 本番の IR 生成順 (m11_gen_ir2.sh → m11_build.sh の後段) を snapshot に当てて、
#   通常 boot (stage4) と survey と trap 位置を測る。既存の測定系・pass は変更しない (呼ぶだけ)。
#   使い方: FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/prod_order_942.sh [fix|base]
#   fix : ldfix (修復段 1〜1d) → fix_ld108 → fix_ld115 → fix_src412770 → qstore → alloca → guard699 → guard4fa210
#         (前提: 先に bash tools/m11/ldfix/ldfix_e2e.sh を実行して work/ldfix_fixed.ll を作る)
#   base: snapshot (boot_final3.ll) → qstore → alloca → guard699 → guard4fa210 (ldfix 系の修復を入れない)
#   順序は測定 commit c9d365465 の m11_gen_ir2.sh (ldfix → ld108 → ld115 → src412770) と m11_build.sh (qstore → alloca → guard699 → guard4fa210) に合わせる。
#   注: fix_r8b815050.py (main の 5c43ea98a・#1448 で入り m11_gen_ir2.sh が既定で適用する) は含めない。r8b を含めた判定は #3608。
#   注: fix_ld115 / guard699 / guard4fa210 は weak 化の前の定義 (define i64 @...) を照合する (m11_build.sh も weak 化の前に走る)。
#       本スクリプトは照合対象の 4 関数の define 行だけ一時的に weak を外し、チェーンの最後で戻す。
set -uo pipefail
MODE="${1:-fix}"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
cd "$REPO"
source "$REPO/tools/shared/env.sh"
PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
IMG="$REPO/tools/m11/work/m11_image.bin"
if [ "$MODE" = fix ]; then
  SRC="$HERE/work/ldfix_fixed.ll"; NAME=prod942; CF=(-DM11_OV_NO_450560)
  [ -f "$SRC" ] || { echo "[prod_order_942] $SRC 無し (先に bash tools/m11/ldfix/ldfix_e2e.sh)"; exit 2; }
elif [ "$MODE" = base ]; then
  SRC="$REPO/tools/m11/work/boot_final3.ll"; NAME=prod942base; CF=()
else
  echo "[prod_order_942] MODE は fix か base"; exit 2
fi
W="$HERE/work/prod942_$MODE"
mkdir -p "$W"
FUNCS='function_8c5eb0|function_8ca670|function_4fa210|function_666a60'
unweak() { sed -E "s/^define weak (i64 @($FUNCS)\\()/define \\1/" "$1" > "$2"; }
reweak() { sed -E "s/^define (i64 @($FUNCS)\\()/define weak \\1/" "$1" > "$2"; }

unweak "$SRC" "$W/src_u.ll"
if [ "$MODE" = fix ]; then
  python3 "$HERE/fix_ld108.py" "$W/src_u.ll" "$W/ld108.ll" || { echo "[prod_order_942] fix_ld108 失敗"; exit 1; }
  python3 "$HERE/fix_ld115.py" "$W/ld108.ll" "$W/ld115.ll" --pe "$PE" > "$W/ld115.log" 2>&1 || { echo "[prod_order_942] fix_ld115 失敗"; exit 1; }
  python3 "$HERE/fix_src412770.py" "$W/ld115.ll" "$W/src412770.ll" || { echo "[prod_order_942] fix_src412770 失敗"; exit 1; }
  Q_IN="$W/src412770.ll"
else
  Q_IN="$W/src_u.ll"
fi
python3 "$REPO/tools/m11/qstore/m11_qstore.py" "$Q_IN" "$W/qstore.ll" --pe "$PE" --report "$W/qstore_report.json" > "$W/qstore.log" 2>&1 || { echo "[prod_order_942] qstore 失敗"; exit 1; }
python3 "$REPO/tools/m11/alloca/m11_alloca.py" "$W/qstore.ll" "$W/alloca.ll" --report "$W/alloca_report.json" > "$W/alloca.log" 2>&1 || { echo "[prod_order_942] m11_alloca.py 失敗"; exit 1; }
python3 "$REPO/tools/m11/guard699/m11_guard699.py" "$W/alloca.ll" "$W/g699.ll" --mode on --cond "icmp sle i32 %9, 0" --report "$W/guard699_report.json" > "$W/guard699.log" 2>&1 || { echo "[prod_order_942] guard699 失敗"; exit 1; }
python3 "$REPO/tools/m11/guard4fa210/m11_guard4fa210.py" "$W/g699.ll" "$W/g4.ll" --mode on --report "$W/guard4fa210_report.json" > "$W/guard4fa210.log" 2>&1 || { echo "[prod_order_942] guard4fa210 失敗"; exit 1; }
reweak "$W/g4.ll" "$W/prod.ll"
tail -1 "$W/qstore.log" | cut -c1-200; tail -1 "$W/guard699.log"; tail -1 "$W/guard4fa210.log"

S4_EXTRA_CF="${CF[*]:-}" bash "$HERE/stage4.sh" "$W/prod.ll" "$NAME" > "$W/stage4.log" 2>&1 || { echo "[prod_order_942] stage4 build 失敗"; tail -3 "$W/stage4.log"; exit 1; }
S4_NAME=$NAME S4_IMAGE=$IMG timeout 300 node "$HERE/run_stage4.mjs" 2>/dev/null | grep M11_RESULT | python3 -c "
import json, sys
d = json.loads(sys.stdin.read().split('M11_RESULT ', 1)[1])
print('STAGE4 $MODE', {k: d.get(k) for k in ['units_run', 'init_count', 'icall_ok', 'dllmain_done', 'threw']})"
S4_NAME=$NAME S4_IMAGE=$IMG timeout 900 node "$HERE/survey_stage4.mjs" 2>/dev/null | grep -o 'M11_SURVEY {.*}' | python3 -c "
import json, sys
d = json.loads(sys.stdin.read().split('M11_SURVEY ', 1)[1])
print('SURVEY $MODE', {k: d.get(k) for k in ['ok', 'miss', 'trap', 'trap_kinds', 'boot_threw']})"
S4_NAME=$NAME S4_IMAGE=$IMG timeout 600 node "$HERE/trap_units.mjs" 2>/dev/null | grep TRAP_UNITS | sed 's/^TRAP_UNITS //' > "$W/trap_units.json"
python3 -c "
import json
d = json.load(open('$W/trap_units.json'))
print('TRAP units', len(d))
for t in d:
    ch = t.get('chain') or []
    print(t['i'], t['va'], t['kind'][:30], t['frame'], ' '.join(f'{f}@{p}' for f, p in ch[:3]))"
