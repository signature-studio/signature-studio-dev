#!/usr/bin/env bash
# run_matrix.sh — 表あり/表空 × 表に有る/無い target の 4 試行を 1 回ずつ別プロセスで流す (#4299)。
# 前提: build.py が $RUNNER_TEMP/ott_getparam/probe_{full,empty}/ott_getparam.cjs を作っていること。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
W="${RUNNER_TEMP:-/tmp/opencode}/ott_getparam"
SITE=18011e5a0
for v in full empty; do
  for t in 8011e7b0 8011e7b1; do
    timeout 60 node "$HERE/drive.mjs" "$W/probe_$v/ott_getparam.cjs" "$t" "$SITE" 2>/dev/null
  done
done
