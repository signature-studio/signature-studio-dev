#!/usr/bin/env bash
# M11 lift: RetDec select-ranges → <name>.drc.ll → (m2 normalize + m5 ir5_patch) → <name>.lift.ll
# 使い方: bash tools/m11/m11_lift.sh <ranges_file> <name> [timeout_sec]
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
source ../shared/env.sh   # FL_WIN64_DIR (#680: PE は env 経由)
mkdir -p work
BIN="${M11_PE:-${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}}"
export TMPDIR="$HERE/work/tmp"
mkdir -p work/tmp

RANGES="${1}"
if [ -f "$1" ]; then RANGES="$(cat "$1")"; fi
NAME="$2"
TMO="${3:-2400}"
NFN="$(echo "$RANGES" | tr ',' '\n' | wc -l)"
echo "[lift] $NAME: ranges=$NFN timeout=$TMO"
RETDEC_BIN="${RETDEC:-$(command -v retdec-decompiler || true)}"
[ -n "$RETDEC_BIN" ] || RETDEC_BIN="$RETDEC_ROOT/bin/retdec-decompiler"
[ -x "$RETDEC_BIN" ] || { echo "[lift] FAIL: retdec-decompiler 無し (RETDEC_ROOT=${RETDEC_ROOT:-unset}; REFERENCES [RETDEC])" >&2; exit 1; }
"$RETDEC_BIN" "$BIN" -o "work/$NAME.drc.c" \
  --select-ranges "$RANGES" --select-decode-only --timeout "$TMO" \
  > "work/$NAME.retdec.log" 2>&1
touch "work/$NAME.retdec.DONE"
[ -f "work/$NAME.drc.ll" ] || { echo "[lift] FAIL: $NAME.drc.ll 未生成" >&2; tail -20 "work/$NAME.retdec.log"; exit 1; }
echo "[lift] RetDec OK: $(wc -l < "work/$NAME.drc.ll") lines ($NAME.drc.ll)"

python3 ../m2/ir_normalize.py "work/$NAME.drc.ll" "work/$NAME.norm0.ll"
python3 ../m5/ir5_patch.py "work/$NAME.norm0.ll" "work/$NAME.lift.ll" \
  --report "work/$NAME.ir5.json" 2>&1 | tail -6 || true
touch "work/$NAME.lift.DONE"
echo "[lift] ir5 OK: $(wc -l < "work/$NAME.lift.ll") lines ($NAME.lift.ll)"
