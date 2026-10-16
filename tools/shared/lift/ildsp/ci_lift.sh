#!/usr/bin/env bash
# GeneralPitchShifter_CreateInstance (0x1aa290) 単独 closure (36 関数・961 命令) の RetDec 入力作成と census (T-SH-62 #3300)。
#   ci_ranges.py (closure 範囲・x86 照合) -> RetDec --select-ranges -> ci_census.py (define 検査・IR の内訳)
# usage: FL_WIN64_DIR=<fl-win64 展開先> [RETDEC_BIN=<[RETDEC] の bin/retdec-decompiler>] bash tools/shared/lift/ildsp/ci_lift.sh   (外部ツールの場所は docs/REFERENCES.md §1 の [RETDEC])
# 出力: tools/shared/work/lift/ci/ (gitignore)。wasm 化・native 差分は未実装 (REPORT_CI.md §5)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
source "$ROOT/env.sh"
PE="$FL_WIN64_DIR/extracted/block24360_PE.bin"
[ -f "$PE" ] || { echo "[ci] block24360_PE.bin not found: $PE"; exit 2; }
W="$ROOT/work/lift/ci"; mkdir -p "$W"
RETDEC="${RETDEC_BIN:-retdec-decompiler}"
cp "$PE" "$W/pe.bin"
python3 "$HERE/ci_ranges.py" "$W/pe.bin" "$W/ranges.json"
RANGES=$(python3 -c "import json;print(','.join(json.load(open('$W/ranges.json'))['ranges_va']))")
"$RETDEC" "$W/pe.bin" -o "$W/ci.drc.c" --select-ranges "$RANGES" --select-decode-only --timeout 500 > "$W/retdec.log" 2>&1
echo "[ci] retdec: $(grep -c '^define' "$W/ci.drc.ll") define (範囲 36)"
python3 "$HERE/ci_restore_stores.py" "$W/ci.drc.ll" "$W/ci.rs.ll"
python3 "$HERE/ci_census.py" "$W/ci.drc.ll" "$W/ranges.json" "$W/ci.rs.ll"
python3 "$ROOT/lift/libkio/ir_normalize.py" "$W/ci.rs.ll" "$W/ci.rs_norm.ll" > /dev/null
python3 "$ROOT/lift/libreverb/gen_helpers.py" "$W/ci.rs_norm.ll" "$W/ci_helpers.c"
# emcc (LLVM 21 系) は RetDec 出力の use-list 指令 (順序メタ情報・意味なし) を受け付けない。除いてから IR→obj まで通す (REPORT_CI §8)。
source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1
grep -v '^ *uselistorder ' "$W/ci.rs_norm.ll" > "$W/ci.emc.ll"
emcc -c -O1 -w "$W/ci.emc.ll" -o "$W/ci.emc.o"
emcc -c -O1 -w "$W/ci_helpers.c" -o "$W/ci_helpers.o"
echo "[ci] emcc obj OK (uselistorder 除去後の IR と helper)"
