#!/usr/bin/env bash
# P8 (PERF-P8 / #166): plugin 別 module vs 動的リンクの 1 コマンド E2E。
#   bash tools/perf/p8/p8.sh            全段 (build → node → Chrome → tables → check)
#   P8_QUICK=1 bash tools/perf/p8/p8.sh 縮小 (N=1,4 / reps 3 / runs 1)
# 前提: emsdk (/opt/emsdk 既定 = EMSDK_DIR), google-chrome (CHROME), node。成果物は work/ (gitignore)、結果は results/。
set -euo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/env.sh"
cd "$P8_DIR"
if [ "${P8_QUICK:-0}" = 1 ]; then NS=1,4; NSL=1,4; REPS=3; RUNS=1; else NS=1,4,16; NSL=1,4,16,64; REPS=9; RUNS=3; fi
rm -f results/p8.jsonl
bash build.sh 16 2>&1 | grep -v INFO
P8_NST=1 P8_SUFFIX=_light bash build.sh 16 2>&1 | grep -v INFO
for rt in bench chrome_p8; do
  f=$rt.mjs; [ $rt = bench ] && f=bench.mjs
  node $f steady --n $NS --reps $REPS --runs $RUNS > /dev/null
  node $f steady --n $NSL --reps $REPS --runs $RUNS --sfx _light > /dev/null
  node $f startup --n $NSL --reps 5 > /dev/null
  node $f memory --n 1,4,16,64,128 > /dev/null
done
node tables.mjs > /dev/null
node check.mjs
node check.mjs --negative
echo "done: $P8_RESULTS/TABLES.md"
