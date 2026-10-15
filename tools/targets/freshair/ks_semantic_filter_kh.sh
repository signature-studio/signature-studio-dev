#!/usr/bin/env bash
# KH HeartCore の Filter process (0x1804655e0) を同一入力の実機機械語で実行し、出力の要約を出す。
#   usage: bash tools/targets/freshair/ks_semantic_filter_kh.sh [N=200] [SEED=7]
# 前提: ../kilohearts/work/winpkg/HeartCore.core_64 が展開済み (work-liftlib-targets)。出力: work/semantic_filter_kh/
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$HERE"
REPO="$(cd -- "$HERE/../../.." && pwd)"
KH="${KH_CORE:-$REPO/tools/targets/kilohearts/work/winpkg/HeartCore.core_64}"
N="${1:-200}"; SEED="${2:-7}"
W="$FA/work/semantic_filter_kh"; mkdir -p "$W"; cd "$W"
clang -O1 -w -o ks_semantic_filter_kh "$HERE/ks_semantic_filter_kh.c" -lm
IN_DUMP=1 ./ks_semantic_filter_kh "$KH" "$N" "$SEED" > kh.txt 2> kh_in.txt
python3 - kh.txt kh_in.txt <<'PY'
import math, struct, sys
out = [l.split() for l in open(sys.argv[1])]
inp = {int(l.split()[0][1:]): l.split() for l in open(sys.argv[2])}
cases = len(out); nonfin = 0; samples = 0; changed = 0
for row in out:
    idx = int(row[0][1:]); n = int(row[1].split('=')[1])
    ol, orr = row[7], row[8]
    il, ir = inp[idx][1], inp[idx][2]
    L = [struct.unpack('<f', bytes.fromhex(ol[i:i+8]))[0] for i in range(0, 8 * n, 8)]
    R = [struct.unpack('<f', bytes.fromhex(orr[i:i+8]))[0] for i in range(0, 8 * n, 8)]
    for i in range(n):
        samples += 1
        if not (math.isfinite(L[i]) and math.isfinite(R[i])): nonfin += 1
        if ol[8*i:8*i+8] != il[8*i:8*i+8] or orr[8*i:8*i+8] != ir[8*i:8*i+8]: changed += 1
print(f"cases={cases} samples={samples} nonfinite={nonfin} changed_vs_input={changed}")
PY
