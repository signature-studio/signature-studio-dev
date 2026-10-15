#!/usr/bin/env bash
# FA-41 (#3534): KH Compressor の P フィールドの感度掃引。ks_kh_comp.sh の出力 (kh_a.txt) を基準に、
# P+OFF を NEG_MUL 倍したときに出力 (L/R/state/通知) が変わる case 数を数える。
#   usage: bash tools/targets/freshair/ks_kh_comp_sens.sh [N=200] [SEED=7] [OFFS="0x0 0x4 0x10 0x14 0x1c"] [MULS="0 1e-6 1e6 -1 0.5"]
# 前提: ks_kh_comp.sh N SEED を先に実行済み (work/kh_comp/n<N>_s<SEED>/kh_a.txt がある)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
KH="${KH_CORE:-$REPO/tools/targets/kilohearts/work/winpkg/HeartCore.core_64}"
N="${1:-200}"; SEED="${2:-7}"
OFFS="${3:-0x0 0x4 0x10 0x14 0x1c}"; MULS="${4:-0 1e-6 1e6 -1 0.5}"
W="$HERE/work/kh_comp/n${N}_s${SEED}"
[ -f "$W/kh_a.txt" ] || { echo "missing: $W/kh_a.txt (先に ks_kh_comp.sh $N $SEED を実行)" >&2; exit 2; }
cd "$W"
for off in $OFFS; do
  for m in $MULS; do
    CHECK_NEG=1 NEG_OFF=$off NEG_MUL=$m ./ks_kh_comp_native "$KH" "$N" "$SEED" > sens.txt 2>/dev/null || true
    echo "P+$off x$m: changed=$(diff kh_a.txt sens.txt | grep -c '^<') / $N"
  done
done
