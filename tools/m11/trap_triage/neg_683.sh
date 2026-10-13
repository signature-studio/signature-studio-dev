#!/usr/bin/env bash
# #683: function_414ad0 の C 転記 (m11_ov.c, M11_OV_414AD0) の survey 実測と、ネガコン (M11_OV_414AD0=0 = 転記を外す)。
# 使い方: bash tools/m11/trap_triage/neg_683.sh   (前提: tools/m11/work/ 展開済み = work-m11。emsdk は m11_build.sh が source する)
# 出力: work/trap_triage/{on,off}.json と survey_diff の表。判定 (受入条件) は REPORT_683.md に書く。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE/.."
mkdir -p work/trap_triage
for v in 1 0; do
  name=$([ "$v" = 1 ] && echo on || echo off)
  s=$(date +%s.%N)
  M11_OV_414AD0=$v bash m11_build.sh > "work/trap_triage/build_$name.log" 2>&1
  b=$(date +%s.%N)
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
