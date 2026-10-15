#!/usr/bin/env bash
# prod_order_3608.sh — #3608: 本番の IR 生成順のうち段を選んで snapshot に当て、stage4 / survey / trap 位置を測る (段別 A/B)。
#   使い方: FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/prod_order_3608.sh NAME INPUT STAGES
#     INPUT  : fix (work/ldfix_fixed.ll・先に ldfix_e2e.sh) | raw (tools/m11/work/boot_final3.ll)
#     STAGES : カンマ区切り (空可)。適用順は main の m11_gen_ir2.sh → m11_build.sh に固定:
#              ld108,ld115,src412770,r8b,qstore,alloca,guard699,guard4fa210
#   prod_order_942.sh との違い: 段を選べる。r8b (main の m11_gen_ir2.sh で既定適用・#1448) を段に含められる。
#   既存の pass・測定系は変更しない (呼ぶだけ)。出力: work/p3608/NAME/ (summary.txt・trap_units.json)。
set -uo pipefail
NAME="${1:?NAME}"; INPUT="${2:?fix|raw}"; STAGES="${3:-}"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
cd "$REPO"
source "$REPO/tools/shared/env.sh"
PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
IMG="$REPO/tools/m11/work/m11_image.bin"
case "$INPUT" in
  fix) SRC="$HERE/work/ldfix_fixed.ll"; CF=(-DM11_OV_NO_450560)
       [ -f "$SRC" ] || { echo "[prod_order_3608] $SRC 無し (先に bash tools/m11/ldfix/ldfix_e2e.sh)"; exit 2; } ;;
  raw) SRC="$REPO/tools/m11/work/boot_final3.ll"; CF=() ;;
  *) echo "[prod_order_3608] INPUT は fix か raw"; exit 2 ;;
esac
W="$HERE/work/p3608/$NAME"
rm -rf "$W"; mkdir -p "$W"
FUNCS='function_8c5eb0|function_8ca670|function_4fa210|function_666a60'
unweak() { sed -E "s/^define weak (i64 @($FUNCS)\\()/define \\1/" "$1" > "$2"; }
reweak() { sed -E "s/^define (i64 @($FUNCS)\\()/define weak \\1/" "$1" > "$2"; }
has() { case ",$STAGES," in *",$1,"*) return 0 ;; esac; return 1; }

unweak "$SRC" "$W/cur0.ll"
cur="$W/cur0.ll"
if has ld108; then
  python3 "$HERE/fix_ld108.py" "$cur" "$W/ld108.ll" > "$W/ld108.log" 2>&1 || { echo "[prod_order_3608] ld108 失敗"; exit 1; }; cur="$W/ld108.ll"
fi
if has ld115; then
  python3 "$HERE/fix_ld115.py" "$cur" "$W/ld115.ll" --pe "$PE" > "$W/ld115.log" 2>&1 || { echo "[prod_order_3608] ld115 失敗"; exit 1; }; cur="$W/ld115.ll"
fi
if has src412770; then
  python3 "$HERE/fix_src412770.py" "$cur" "$W/src412770.ll" > "$W/src412770.log" 2>&1 || { echo "[prod_order_3608] src412770 失敗"; exit 1; }; cur="$W/src412770.ll"
fi
if has r8b; then
  python3 "$HERE/fix_r8b815050.py" "$cur" "$W/r8b.ll" --pe "$PE" > "$W/r8b.log" 2>&1 || { echo "[prod_order_3608] r8b 失敗"; tail -3 "$W/r8b.log"; exit 1; }; cur="$W/r8b.ll"
fi
if has qstore; then
  python3 "$REPO/tools/m11/qstore/m11_qstore.py" "$cur" "$W/qstore.ll" --pe "$PE" --report "$W/qstore_report.json" > "$W/qstore.log" 2>&1 || { echo "[prod_order_3608] qstore 失敗"; exit 1; }; cur="$W/qstore.ll"
fi
if has alloca; then
  python3 "$REPO/tools/m11/alloca/m11_alloca.py" "$cur" "$W/alloca.ll" --report "$W/alloca_report.json" > "$W/alloca.log" 2>&1 || { echo "[prod_order_3608] alloca 失敗"; exit 1; }; cur="$W/alloca.ll"
fi
if has guard699; then
  python3 "$REPO/tools/m11/guard699/m11_guard699.py" "$cur" "$W/g699.ll" --mode on --cond "icmp sle i32 %9, 0" --report "$W/guard699_report.json" > "$W/guard699.log" 2>&1 || { echo "[prod_order_3608] guard699 失敗"; exit 1; }; cur="$W/g699.ll"
fi
if has guard4fa210; then
  python3 "$REPO/tools/m11/guard4fa210/m11_guard4fa210.py" "$cur" "$W/g4.ll" --mode on --report "$W/guard4fa210_report.json" > "$W/guard4fa210.log" 2>&1 || { echo "[prod_order_3608] guard4fa210 失敗"; exit 1; }; cur="$W/g4.ll"
fi
reweak "$cur" "$W/prod.ll"

S4_EXTRA_CF="${CF[*]:-}" bash "$HERE/stage4.sh" "$W/prod.ll" "p3608_$NAME" > "$W/stage4.log" 2>&1 || { echo "[prod_order_3608] stage4 build 失敗"; tail -3 "$W/stage4.log"; exit 1; }
S4_NAME="p3608_$NAME" S4_IMAGE=$IMG timeout 300 node "$HERE/run_stage4.mjs" 2>/dev/null | grep M11_RESULT | python3 -c "
import json, sys
d = json.loads(sys.stdin.read().split('M11_RESULT ', 1)[1])
print('STAGE4 $NAME', {k: d.get(k) for k in ['units_run', 'init_count', 'icall_ok', 'dllmain_done', 'threw']})" | tee "$W/summary.txt"
S4_NAME="p3608_$NAME" S4_IMAGE=$IMG timeout 900 node "$HERE/survey_stage4.mjs" 2>/dev/null | grep -o 'M11_SURVEY {.*}' | python3 -c "
import json, sys
d = json.loads(sys.stdin.read().split('M11_SURVEY ', 1)[1])
print('SURVEY $NAME', {k: d.get(k) for k in ['ok', 'miss', 'trap', 'trap_kinds', 'boot_threw']})" | tee -a "$W/summary.txt"
S4_NAME="p3608_$NAME" S4_IMAGE=$IMG timeout 600 node "$HERE/trap_units.mjs" 2>/dev/null | grep TRAP_UNITS | sed 's/^TRAP_UNITS //' > "$W/trap_units.json"
python3 -c "
import json
d = json.load(open('$W/trap_units.json'))
print('TRAP $NAME', len(d), ' '.join('%s:%s' % (t['i'], 'halt0' if t['kind'].startswith('halt0') else 'OOB') for t in d))" | tee -a "$W/summary.txt"
