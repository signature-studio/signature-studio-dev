#!/usr/bin/env bash
# tools/perf 1 コマンド E2E: 入力コピー → ビルドマトリクス → node/Chrome 実測 → 巨大 wasm 実験 → 表生成
#   bash tools/perf/perf.sh            # 全段 (数十分; 16 コア共有環境では load 依存で結果が揺れる)
#   PERF_QUICK=1 bash tools/perf/perf.sh   # 代表変種のみ・反復 1 (数分)
#   PERF_STAGES="inputs build node chrome huge tables" で段を選択
# 前提: /opt/emsdk, node(pnpm 26), google-chrome, wabt/binaryen (wasm-objdump)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/flags.sh"
STAGES="${PERF_STAGES:-inputs build node chrome huge tables}"
Q="${PERF_QUICK:-0}"
REPS=3; [ "$Q" = 1 ] && REPS=1
has() { [[ " $STAGES " == *" $1 "* ]]; }
fail=0
if has inputs; then bash "$HERE/lib/inputs.sh" || exit 2; fi
if has build; then
  if [ "$Q" = 1 ]; then bash "$HERE/build/ott_matrix.sh" o0 o2 o3 o2simd o3lto o3ltosimd o2raw || fail=1
  else bash "$HERE/build/ott_matrix.sh" o0 o0min o1 o2 o3 os oz o0simd o1simd o2simd o3simd ossimd o2lto o3lto o2ltosimd o3ltosimd oslto o2thinlto o3thinlto o3lto_m1flags o3lto_wasmopt o2fullnogc o2fullgc o2m1flags o2thr o2thrsimd o2raw o3raw o2rawsimd || fail=1
    bash "$HERE/build/wasmopt_matrix.sh" >/dev/null || fail=1; fi
  for k in a1 a2; do for v in "o0 -O0" "o1 -O1" "o2 -O2" "o3 -O3" "o1simd -O1 -msimd128" "o2simd -O2 -msimd128" "o3simd -O3 -msimd128"; do
    bash "$HERE/build/m5_build.sh" $k $v >/dev/null || fail=1; done; done
fi
cd "$HERE/harness"
if has node; then
  V=$(ls ../work/ott | grep -v '^wo_' | tr '\n' ',' | sed 's/,$//'); [ "$Q" = 1 ] && V=o0,o2,o3,o2simd,o3lto,o3ltosimd
  node node_bench.mjs ott_all ott "$V" --reps "$REPS" --iters 20000
  node node_bench.mjs m5_a1 a1 o0,o1,o2,o3,o1simd,o2simd,o3simd --modes default,liftoff,tf --reps "$REPS" --iters 20000
  node node_bench.mjs m5_a2 a2 o0,o1,o2,o3,o1simd,o2simd,o3simd --modes default,liftoff,tf --reps "$REPS" --iters 20000
  [ "$Q" = 1 ] || { node node_bench.mjs ott_tier ott o0,o2,o2simd,o3,o2lto --modes liftoff,tf --reps 3 --iters 20000
                    WO=$(ls ../work/ott | grep '^wo_' | tr '\n' ',' | sed 's/,$//'); node node_bench.mjs ott_wo ott "$WO" --reps 3 --iters 20000; }
fi
if has chrome; then
  V=o0,o2,o3,o2simd,o3lto,o3ltosimd; [ "$Q" = 1 ] || V=o0,o1,o2,o3,os,o2simd,o3simd,o2lto,o3lto,o3ltosimd,oslto,o2thinlto,o3thinlto,o2thr
  node chrome_bench.mjs ott_all ott "$V" --reps "$REPS" --iters 20000
  [ "$Q" = 1 ] || { node chrome_bench.mjs ott_tier ott o0,o2,o3lto --modes liftoff,tf --reps 2 --iters 20000
    node chrome_bench.mjs m5_a1 a1 o0,o1,o2,o3,o2simd,o3simd --modes default,liftoff,tf --reps 2 --iters 20000
    node chrome_bench.mjs m5_a2 a2 o0,o1,o2,o3,o2simd,o3simd --modes default,liftoff,tf --reps 2 --iters 20000; }
fi
if has huge; then
  cd "$HERE/huge"
  if [ "$Q" = 1 ]; then node huge_chrome.mjs scale --k 1,4,10 --mode stream; node huge_chrome.mjs idb; node huge_chrome.mjs mem
  else
    node huge_chrome.mjs scale --k 1,4,10,30,60,100 --mode stream,bytes --flags default,eager
    node huge_chrome.mjs cores --kk 30 --flags eager
    node huge_chrome.mjs hints
    node huge_chrome.mjs limits; node huge_chrome.mjs funcs; node huge_chrome.mjs sync; node huge_chrome.mjs idb; node huge_chrome.mjs mem
    node huge_chrome.mjs worklet --variants o0,o2; node huge_chrome.mjs bw --kk 10 --mbps 50,100,1000 --mode stream,bytes --flags default,eager; node huge_chrome.mjs worklet --variants ../ottk/o2_k400 --flags default,eager
    node huge_chrome.mjs ottscale --k 1,100,400,800 --flags default,eager
    node huge_chrome.mjs cache --kk 400
  fi
fi
if has tables; then
  cd "$HERE/report"
  { echo "# PERF TABLES (自動生成: $(date -Is))"; echo; echo "## node"; node tables_ott.mjs node; echo; echo "## chrome"; node tables_ott.mjs chrome; echo; echo "## huge"; node tables_huge.mjs; } > "$RESULTS/TABLES.md"
  echo "[perf] tables → $RESULTS/TABLES.md"
fi
exit $fail
