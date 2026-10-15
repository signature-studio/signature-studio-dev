#!/usr/bin/env bash
# GeneralPitchShifter_CreateInstance (0x1aa290) 単独 closure (36 関数・961 命令) の RetDec 入力作成と census (T-SH-62 #3300)。
#   ci_ranges.py (closure 範囲・x86 照合) -> RetDec --select-ranges -> ci_census.py (define 検査・IR の内訳)
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/ildsp/ci_lift.sh
# 出力: tools/shared/work/lift/ci/ (gitignore)。wasm 化・native 差分は未実装 (REPORT.md §T-SH-62 の子 issue)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
source "$ROOT/env.sh"
PE="$FL_WIN64_DIR/extracted/block24360_PE.bin"
[ -f "$PE" ] || { echo "[ci] block24360_PE.bin not found: $PE"; exit 2; }
W="$ROOT/work/lift/ci"; mkdir -p "$W"
RETDEC="${RETDEC_BIN:-${RETDEC_ROOT:-/opt/retdec}/bin/retdec-decompiler}"
cp "$PE" "$W/pe.bin"
python3 "$HERE/ci_ranges.py" "$W/pe.bin" "$W/ranges.json"
RANGES=$(python3 -c "import json;print(','.join(json.load(open('$W/ranges.json'))['ranges_va']))")
"$RETDEC" "$W/pe.bin" -o "$W/ci.drc.c" --select-ranges "$RANGES" --select-decode-only --timeout 500 > "$W/retdec.log" 2>&1
echo "[ci] retdec: $(grep -c '^define' "$W/ci.drc.ll") define (範囲 36)"
python3 "$HERE/ci_census.py" "$W/ci.drc.ll" "$W/ranges.json"
