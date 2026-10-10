#!/usr/bin/env bash
# node 側 OTT マトリクス実測 (default tier 全変種 + liftoff/tf サブセット) と M5 カーネル
set -uo pipefail
cd "$(dirname "$0")"
export PATH=/home/ubuntu/.local/share/pnpm/bin:$PATH
ALL=$(ls ../work/ott | grep -v '^wo_' | tr '\n' ',' | sed 's/,$//')
WO=$(ls ../work/ott | grep '^wo_' | tr '\n' ',' | sed 's/,$//')
SUB=o0,o2,o2simd,o3,o2lto
node node_bench.mjs ott_all ott "$ALL" --reps ${REPS:-5} --iters 20000
node node_bench.mjs ott_wo ott "$WO" --reps ${REPS:-5} --iters 20000
node node_bench.mjs ott_tier ott "$SUB" --modes liftoff,tf --reps 3 --iters 20000
K5=o0,o1,o2,o3,o1simd,o2simd,o3simd
node node_bench.mjs m5_a1 a1 "$K5" --modes default,liftoff,tf --reps 3 --iters 20000
node node_bench.mjs m5_a2 a2 "$K5" --modes default,liftoff,tf --reps 3 --iters 20000
echo NODEDONE
