#!/usr/bin/env bash
# #683: function_414ad0 の C 版 (m11_ov.c, M11_OV_414AD0) の survey 実測。0 = main と同じ LStrSetLength 版 (既定) / 1 = UStrSetLength 版 (転記)。
# 使い方: bash tools/m11/trap_triage/neg_683.sh   (前提: tools/m11/work/ 展開済み = work-m11。emsdk は m11_build.sh が source する)
# 出力: work/trap_triage/{on,off}.json と survey_diff の表。判定 (受入条件) は REPORT_683.md に書く。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE/.."
source ../shared/env.sh   # FL_WIN64_DIR
PE_QS="${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
# qstore (m11_build.sh) は PE と capstone・pefile が揃わないと skip → build が失敗する。事前に落として原因を明示する
[ -f "$PE_QS" ] || { echo "[neg_683] ERROR: PE 無し: $PE_QS" >&2; exit 1; }
python3 -c 'import capstone, pefile' || { echo "[neg_683] ERROR: capstone / pefile 無し (qstore が走らない)" >&2; exit 1; }
mkdir -p work/trap_triage
for v in 1 0; do
  name=$([ "$v" = 1 ] && echo on || echo off)
  s=$(date +%s.%N)
  M11_OV_414AD0=$v bash m11_build.sh > "work/trap_triage/build_$name.log" 2>&1
  b=$(date +%s.%N)
  [ "$(python3 m11_cond.py --get qstore)" = applied ] || { echo "[neg_683] ERROR: qstore=applied の記録無し (build_$name.log を確認)" >&2; exit 1; }
  node trap_triage/survey_units.mjs "work/trap_triage/$name.json" > "work/trap_triage/survey_$name.log" 2>&1
  e=$(date +%s.%N)
  echo "[neg_683] M11_OV_414AD0=$v build $(awk "BEGIN{print $b - $s}") s / survey $(awk "BEGIN{print $e - $b}") s / loadavg(1,5,15m)=$(cut -d' ' -f1-3 /proc/loadavg)"
  tail -1 "work/trap_triage/build_$name.log"
done
echo "[neg_683] survey_diff ON(new) を OFF(=転記なし) と比較 (A=OFF, B=ON)"
python3 trap_triage/survey_diff.py work/trap_triage/off.json work/trap_triage/on.json
python3 - <<'PYEOF'
import json
for name in ('off', 'on'):
    d = {r['unit']: r for r in json.load(open('work/trap_triage/%s.json' % name))}
    print('%-4s units 149/158/280/659: %s' % (name, [(u, d[u]['kind']) for u in (149, 158, 280, 659)]))
PYEOF
