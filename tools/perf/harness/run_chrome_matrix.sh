#!/usr/bin/env bash
# Chrome (headless=new, Worker) 側 OTT / M5 実測
set -uo pipefail
cd "$(dirname "$0")"
export PATH=/home/ubuntu/.local/share/pnpm/bin:$PATH
V=o0,o1,o2,o3,os,o2simd,o3simd,o2lto,o3lto,o3ltosimd,oslto,o2thinlto,o3thinlto,o2thr,wo_o2raw_none,wo_o2raw_O3,wo_o2raw_O3conv
node chrome_bench.mjs ott_all ott "$V" --reps ${REPS:-3} --iters 20000
node chrome_bench.mjs ott_tier ott o0,o2,o3lto --modes liftoff,tf --reps 2 --iters 20000
node chrome_bench.mjs m5_a1 a1 o0,o1,o2,o3,o2simd,o3simd --modes default,liftoff,tf --reps 2 --iters 20000
node chrome_bench.mjs m5_a2 a2 o0,o1,o2,o3,o2simd,o3simd --modes default,liftoff,tf --reps 2 --iters 20000
echo CHROMEDONE
