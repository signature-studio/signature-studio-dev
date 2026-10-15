#!/usr/bin/env bash
# M6 lift: RetDec select ranges → ott.drc.ll → (m2 normalize + m5 ir5_patch) → ott_lift.ll
# 再実行: bash tools/m6/m6_lift.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
source "$HERE/../shared/env.sh"
mkdir -p work
BIN="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"
export TMPDIR="$HERE/work/tmp"

RANGES="$(cat work/ott_ranges.txt)"
echo "[lift] ranges: $(echo "$RANGES" | tr ',' '\n' | wc -l) functions"
/opt/retdec/bin/retdec-decompiler "$BIN" -o work/ott.drc.c \
  --select-ranges "$RANGES" --select-decode-only --timeout 2400 \
  > work/ott.retdec.log 2>&1
[ -f work/ott.drc.ll ] || { echo "[lift] FAIL: ott.drc.ll 未生成" >&2; tail -20 work/ott.retdec.log; exit 1; }
echo "[lift] RetDec OK: $(wc -l < work/ott.drc.ll) lines (ott.drc.ll)"

python3 ../m2/ir_normalize.py work/ott.drc.ll work/ott_norm0.ll
echo "[lift] normalize OK: $(wc -l < work/ott_norm0.ll) lines (ott_norm0.ll)"

python3 ../m5/ir5_patch.py work/ott_norm0.ll work/ott_lift.ll --report work/ir5_report.json 2>&1 | tail -5 || true
[ -f work/ott_lift.ll ] || { echo "[lift] FAIL: ir5_patch" >&2; exit 1; }
echo "[lift] ir5_patch OK: $(wc -l < work/ott_lift.ll) lines (ott_lift.ll)"
