#!/usr/bin/env bash
# P8 実 OTT 版 (PERF-P8 / #166): bit-exact OTT (x64c lift) を plugin 別 instance で N 個駆動する node 計測。
#   bash tools/perf/p8/real/p8_real.sh            N = 1 2 4 8 16 (既定)
#   NS="1 4" bash tools/perf/p8/real/p8_real.sh    N を指定
# 前提: tools/ott/work/lift/ottl.cjs (oc_artifacts: work-m6-ott で展開)。結果 = tools/perf/p8/results/real_ott.jsonl。
# 各 N は別プロセスで計測する (RSS 増分を独立に取るため)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
CJS="${OTT_CJS:-$HERE/../../../ott/work/lift/ottl.cjs}"
[ -f "$CJS" ] || { echo "FATAL: $CJS 無し (oc_artifacts: work-m6-ott が必要)" >&2; exit 1; }
RES="$HERE/../results"; mkdir -p "$RES"; OUT="$RES/real_ott.jsonl"; : > "$OUT"
for n in ${NS:-1 2 4 8 16}; do
  node "$HERE/bench_real.mjs" "$CJS" "$n" >> "$OUT"
  tail -1 "$OUT" | cut -c1-400
done
echo "done: $OUT"
