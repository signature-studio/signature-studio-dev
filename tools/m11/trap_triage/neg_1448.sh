#!/usr/bin/env bash
# #1448: fix_r8b815050 (function_815050 の 6cefb0 第 3 引数 = 機械語の即値 1) の survey 実測。1 = 修復あり (既定) / 0 = 修復なし (A/B・ネガコン)。
# 使い方: bash tools/m11/trap_triage/neg_1448.sh   (前提: tools/m11/work/ 展開済み = work-m11、FL_WIN64_DIR 展開済み。emsdk は m11_build.sh が source する)
# 出力: work/trap_triage/{on,off}.json と survey_diff の表。判定 (受入条件) は REPORT_683.md §8.1 に書く。
# IR は v ごとに m11_gen_ir2.sh で作り直す (修復の有無だけが違う IR で build する)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE/.."
source ../shared/env.sh   # FL_WIN64_DIR
PE_QS="${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
[ -f "$PE_QS" ] || { echo "[neg_1448] ERROR: PE 無し: $PE_QS" >&2; exit 1; }
python3 -c 'import capstone, pefile' || { echo "[neg_1448] ERROR: capstone / pefile 無し (ldfix・qstore が走らない)" >&2; exit 1; }
mkdir -p work/trap_triage
for v in 1 0; do
  name=$([ "$v" = 1 ] && echo on || echo off)
  s=$(date +%s.%N)
  M11_FIX_R8B=$v bash m11_gen_ir2.sh > "work/trap_triage/gen_$name.log" 2>&1
  M11_ALLOW_R8B_DISABLED=1 bash m11_build.sh > "work/trap_triage/build_$name.log" 2>&1
  b=$(date +%s.%N)
  [ "$(python3 m11_cond.py --get qstore)" = applied ] || { echo "[neg_1448] ERROR: qstore=applied の記録無し (build_$name.log を確認)" >&2; exit 1; }
  node trap_triage/survey_units.mjs "work/trap_triage/$name.json" > "work/trap_triage/survey_$name.log" 2>&1
  e=$(date +%s.%N)
  echo "[neg_1448] M11_FIX_R8B=$v gen+build $(awk "BEGIN{print $b - $s}") s / survey $(awk "BEGIN{print $e - $b}") s / loadavg(1,5,15m)=$(cut -d' ' -f1-3 /proc/loadavg)"
  tail -1 "work/trap_triage/build_$name.log"
done
echo "[neg_1448] survey_diff ON (修復あり) を OFF (修復なし) と比較 (A=OFF, B=ON)"
python3 trap_triage/survey_diff.py work/trap_triage/off.json work/trap_triage/on.json
python3 - <<'PYEOF'
import json
for name in ('off', 'on'):
    d = {r['unit']: r for r in json.load(open('work/trap_triage/%s.json' % name))}
    print('%-4s units 149/158/280/659: %s' % (name, [(u, d[u]['kind']) for u in (149, 158, 280, 659)]))
PYEOF
