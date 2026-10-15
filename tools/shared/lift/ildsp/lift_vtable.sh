#!/usr/bin/env bash
# ildsp GeneralPitchShifter vtable 転送先 (既定 0x161fc0) の closure を lift する前段 (T-SH-61 #3299)。
#   ildsp_vtable.py -> ildsp_vtable_check.py (生バイト検算) -> closure_select.py (closure の絶対 VA 範囲) -> RetDec --select-ranges
#   -> ir_normalize (libkio) -> gen_helpers (libreverb)。gen_helpers が未対応 op で止まるのは意図した未達 (wasm 化は子 issue)。
# usage: FL_WIN64_DIR=<fl-win64 展開先> RETDEC_BIN=<retdec-decompiler> bash tools/shared/lift/ildsp/lift_vtable.sh [target_rva]
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
source "$ROOT/env.sh"
T="${1:-0x161fc0}"
W="${ILDSP_WORK:-$ROOT/work/lift/ildsp}/$T"; mkdir -p "$W"
PE="${ILDSP_PE:-$FL_WIN64_DIR/extracted/block24360_PE.bin}"
RETDEC="${RETDEC_BIN:-/opt/retdec/bin/retdec-decompiler}"
python3 "$ROOT/scripts/ildsp_vtable.py" "$PE" --out "$W/ildsp_vtable.json" > "$W/vtable.log"
python3 "$ROOT/scripts/ildsp_vtable_check.py" "$W/ildsp_vtable.json" > "$W/vtable_check.log"
python3 "$HERE/closure_select.py" "$W/ildsp_vtable.json" "$PE" "$T" "$W/ranges.txt" | tee "$W/closure.log"
"$RETDEC" "$PE" -o "$W/ildsp.drc.c" --select-ranges "$(cat "$W/ranges.txt")" --select-decode-only --timeout 600 > "$W/retdec.log" 2>&1
echo "[ildsp] retdec: $(grep -c '^define' "$W/ildsp.drc.ll") functions lifted"
python3 "$ROOT/lift/libkio/ir_normalize.py" "$W/ildsp.drc.ll" "$W/norm_raw.ll" > /dev/null
echo "[ildsp] declared helper op names (declare @__asm_*): $(grep '^declare' "$W/norm_raw.ll" | grep -oE '@__asm_[a-z0-9]+' | sort -u | wc -l) distinct"
python3 "$HERE/../libreverb/gen_helpers.py" "$W/norm_raw.ll" "$W/helpers.c"
echo "[ildsp] helpers ok"
