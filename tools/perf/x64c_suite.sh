#!/usr/bin/env bash
# bit-exact OTT (tools/ott x64c lift) の RTF を node / Chrome Worker / 実 AudioWorklet / native 実機械語で同一手順に再測 (PERF-P9 #168)。
#   TAG=run1 REPS=3 bash tools/perf/x64c_suite.sh      結果: tools/perf/results/x64c/{node,worker,worklet,worklet-noclock,native}_<TAG>.jsonl
#   env: VARIANTS (既定 o0 o1 o2 o3 o2lto o3lto o3ltosimd) / WL_VARIANTS (worklet 対象; 既定 o0 o2 o3lto o3ltosimd) / BLOCKS (worklet 実時間 block 数; 既定 3000)
# 前提: toolchain-emsdk (EMSDK_DIR) / analysis-ott-binaries (ANALYSIS_DIR) / python capstone,pefile / google-chrome / gcc。 summary は x64c_summary.mjs
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/flags.sh"
TAG="${TAG:-run1}"; REPS="${REPS:-3}"; BLOCKS="${BLOCKS:-3000}"
V="${VARIANTS:-o0 o1 o2 o3 o2lto o3lto o3ltosimd}"; WV="${WL_VARIANTS:-o0 o2 o3lto o3ltosimd}"
OUT="$HERE/results/x64c"; mkdir -p "$OUT"; export PERF_TMP="${PERF_TMP:-${RUNNER_TEMP:-/tmp/opencode}/perf}"; mkdir -p "$PERF_TMP"
csv() { echo "$*" | tr ' ' ','; }
echo "[x64c_suite] tag=$TAG reps=$REPS load(start) $(cut -d' ' -f1-3 /proc/loadavg) node $(node -v) $(${CHROME} --version 2>/dev/null)"
OTT_SKIP_INFO=1 bash "$HERE/../ott/ott_e2e.sh" --quick > "$OUT/ott_e2e_$TAG.log" 2>&1 || { tail -15 "$OUT/ott_e2e_$TAG.log"; echo "[x64c_suite] FAIL: ott_e2e"; exit 1; }
tail -2 "$OUT/ott_e2e_$TAG.log" | sed 's/^/  /'
bash "$HERE/build/ott_x64c_build.sh" $V 2>&1 | grep '^\[x64c\]' | sort | tee "$OUT/build_$TAG.txt"
node "$HERE/harness/x64c_names.mjs" "$HERE/work/ott_x64c" > /dev/null
: > "$OUT/node_$TAG.jsonl"
for r in $(seq 1 "$REPS"); do for v in $V; do node "$HERE/harness/x64c_node.mjs" "$HERE/work/ott_x64c/$v.wasm" >> "$OUT/node_$TAG.jsonl"; done; done
echo "[x64c_suite] node done  load $(cut -d' ' -f1-3 /proc/loadavg)"
: > "$OUT/worker_$TAG.jsonl"; : > "$OUT/worklet_$TAG.jsonl"; : > "$OUT/worklet-noclock_$TAG.jsonl"
node "$HERE/harness/x64c_chrome.mjs" "$TAG" worker "$(csv $V)" --reps "$REPS" 2>&1 | tail -n +1
echo "[x64c_suite] worker done  load $(cut -d' ' -f1-3 /proc/loadavg)"
node "$HERE/harness/x64c_chrome.mjs" "$TAG" worklet "$(csv $WV)" --reps "$REPS" --blocks "$BLOCKS" 2>&1 | tail -n +1
node "$HERE/harness/x64c_chrome.mjs" "$TAG" worklet "$(csv $WV)" --reps "$REPS" --noclock 2>&1 | tail -n +1
echo "[x64c_suite] worklet done  load $(cut -d' ' -f1-3 /proc/loadavg)"
bash "$HERE/native/native_bench.sh" "$((REPS + 2))" 20000 > "$OUT/native_$TAG.jsonl"
echo "[x64c_suite] native done  load $(cut -d' ' -f1-3 /proc/loadavg)"
node "$HERE/harness/x64c_summary.mjs" "$TAG" | tee "$OUT/summary_$TAG.md"
