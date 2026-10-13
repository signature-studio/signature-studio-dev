#!/usr/bin/env bash
# Ghidra ルートの修復 ablation: 全 fix / 1 つ外し / fix なし を 3 snap-in × 1000 trial で突合 (build 失敗も記録)。
#   bash ghidra_route/ablate.sh [trials] [seed]    → 1 行 1 構成 "snap-in | 構成 | build | trials ok/n"
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; KH="$HERE/.."
TR=${1:-1000}; SEED=${2:-7}
ALL=bitcast,intload,stackpair,assoc,concat
for n in gain haas gate; do
  for cfg in "all:$ALL" "none:" "-bitcast:intload,stackpair,assoc,concat" "-intload:bitcast,stackpair,assoc,concat" "-stackpair:bitcast,intload,assoc,concat" "-assoc:bitcast,intload,stackpair,concat" "-concat:bitcast,intload,stackpair,assoc"; do
    label=${cfg%%:*}; fix=${cfg#*:}
    out=$(bash "$HERE/build_cmp.sh" $n $TR $SEED "$fix" 2>&1); rc=$?
    if [ $rc = 3 ]; then echo "$n | $label | emcc FAIL | -"; else echo "$n | $label | ok | $(echo "$out" | grep -o 'RESULT trials [0-9]*/[0-9]*')"; fi
  done
done
