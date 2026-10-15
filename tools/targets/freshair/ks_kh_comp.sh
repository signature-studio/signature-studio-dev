#!/usr/bin/env bash
# FA-38 (#3506): KH Compressor (HeartCore 0x1802abc20) の機械語 harness を実行する。
#   usage: bash tools/targets/freshair/ks_kh_comp.sh [N=200] [SEED=7]
# 前提: work/kh_comp の HeartCore は tools/targets/kilohearts/work/winpkg/HeartCore.core_64 (work-liftlib-targets 展開)。
# 出力: tools/targets/freshair/work/kh_comp/ (gitignore)。判定: ERR 0・決定性 (同 seed 2 回が byte 一致)・
#       負例 (CHECK_NEG=1 NEG_OFF=0x4 NEG_MUL=2 で P+0x4 を ×2) で出力が変わる case が 1 件以上あること。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$HERE"
REPO="$(cd -- "$HERE/../../.." && pwd)"
KH="${KH_CORE:-$REPO/tools/targets/kilohearts/work/winpkg/HeartCore.core_64}"
N="${1:-200}"; SEED="${2:-7}"
W="$FA/work/kh_comp"; mkdir -p "$W"; cd "$W"
cc -O1 -Wall -o ks_kh_comp_native "$HERE/ks_kh_comp_native.c" -lm
echo "load(before): $(cut -d' ' -f1-3 /proc/loadavg)  nproc=$(nproc)"
t0=$(date +%s.%N)
./ks_kh_comp_native "$KH" "$N" "$SEED" > kh_a.txt 2> kh_a.err
t1=$(date +%s.%N)
./ks_kh_comp_native "$KH" "$N" "$SEED" > kh_b.txt 2> kh_b.err
CHECK_NEG=1 NEG_OFF=0x4 NEG_MUL=2.0 ./ks_kh_comp_native "$KH" "$N" "$SEED" > kh_neg.txt 2> kh_neg.err
echo "load(after): $(cut -d' ' -f1-3 /proc/loadavg)"
printf 'run1 (N=%s seed=%s): %.2f s\n' "$N" "$SEED" "$(python3 -c "print($t1 - $t0)")"
echo "run1 $(grep SUMMARY kh_a.err)"
grep UNRES kh_a.err || true
echo "run2 $(grep SUMMARY kh_b.err)"
echo "neg  $(grep SUMMARY kh_neg.err)"
if cmp -s kh_a.txt kh_b.txt; then echo "determinism: run1 == run2 (byte 一致, $(wc -l < kh_a.txt) lines)"; else echo "determinism: MISMATCH"; exit 1; fi
diffs=$(diff kh_a.txt kh_neg.txt | grep -c '^<' || true)
echo "negative control: cases whose output changed under P+0x4 x2 = $diffs / $N"
if [ "$diffs" -lt 1 ]; then echo "negative control FAILED (sensitivity not shown)"; exit 1; fi
if grep -q 'ERR' kh_a.txt; then echo "ERR cases present"; exit 1; fi
echo "RESULT: KH Compressor native harness ran $N/$N with ERR 0"
