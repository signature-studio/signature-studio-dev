#!/usr/bin/env bash
# GeneralPitchShifter vtable slot 4 (RVA 0x1aa3a0 / VA 0x1801aa3a0, 42 insns) の lift + native 実機械語との差分テスト。
#   locate (vtable slot 4 -> 機械語) -> RetDec --select-ranges -> ir_normalize -> emcc -> diff_test (native_ref.c / run_wasm.mjs)
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/ildsp/lift.sh [ok|neg-compare|neg-ir|all]
#   ok (既定)    : 本検査。全ケース一致かつ gate 充足で exit 0。
#   neg-compare  : 比較器のネガティブコントロール (wasm 結果 1 バイト反転) -> FAIL を期待。
#   neg-ir       : IR のネガティブコントロール (ループ2 の buffer store の 0 を 1 に、1 箇所) -> FAIL を期待。
#   neg-*        : FAIL したとき exit 0 / PASS してしまったとき exit 1。
#   all          : ok + 全 neg-* (いずれか期待外れなら非 0)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
source "$ROOT/env.sh"
MODE="${1:-ok}"
if [ "$MODE" = all ]; then
  for m in ok neg-compare neg-ir; do bash "$0" "$m" || exit 1; done; echo "[ildsp] ALL OK (本検査 PASS + ネガコン 2 件が期待通り FAIL)"; exit 0
fi
PE="${GPS_PE:-$FL_WIN64_DIR/extracted/block24360_PE.bin}"
[ -f "$PE" ] || { echo "[ildsp] block24360_PE.bin not found: $PE (FL_WIN64_DIR=$FL_WIN64_DIR)"; exit 2; }
W="$ROOT/work/lift/ildsp/$MODE"; mkdir -p "$W"
EMSDK="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"; RETDEC="${RETDEC_BIN:-/opt/retdec/bin/retdec-decompiler}"
source "$EMSDK" >/dev/null 2>&1
cp "$PE" "$W/GPS.dll"
python3 "$HERE/locate.py" "$W/GPS.dll" "$W/loc"
RANGE=$(python3 -c "import json;print(json.load(open('$W/loc/ranges.json'))['range'])")
FN=$(python3 -c "import json;print(json.load(open('$W/loc/ranges.json'))['fn_name'])")
[ "$FN" = function_1801aa3a0 ] || { echo "[ildsp] unexpected lifted name $FN"; exit 2; }
"$RETDEC" "$W/GPS.dll" -o "$W/gps.drc.c" --select-ranges "$RANGE" --select-decode-only --timeout 600 > "$W/retdec.log" 2>&1
echo "[ildsp] retdec: $(grep -c '^define' "$W/gps.drc.ll") functions lifted (range $RANGE)"
python3 "$HERE/../libkio/ir_normalize.py" "$W/gps.drc.ll" "$W/gps_norm.ll" >/dev/null
# neg-ir: ループ2 (count2 [+0x244] の回) の buffer [+0x260] への store の値 0 を 1 に 1 箇所だけ変える
if [ "$MODE" = neg-ir ]; then
  sed -i 's/store i32 0, ptr %44, align 4/store i32 1, ptr %44, align 4/' "$W/gps_norm.ll"
  [ "$(grep -c 'store i32 1, ptr %44' "$W/gps_norm.ll")" = 1 ] || { echo "[ildsp] neg-ir: target store not unique"; exit 2; }
fi
emcc "$W/gps_norm.ll" -o "$W/fn.wasm" -O1 -w -sSTANDALONE_WASM=1 -sERROR_ON_UNDEFINED_SYMBOLS=0 -sALLOW_MEMORY_GROWTH=0 \
  -sINITIAL_MEMORY=16MB -sSTACK_SIZE=256KB -sGLOBAL_BASE=1024 --no-entry -Wl,--no-gc-sections -Wl,--export=$FN
echo "[ildsp] wasm: $(stat -c %s "$W/fn.wasm") bytes"
ARGS=(); [ "$MODE" = neg-compare ] && ARGS=(--mutate-wasm-result)
set +e; python3 "$HERE/diff_test.py" "$W" "${ARGS[@]}"; RC=$?; set -e
if [[ "$MODE" == neg-* ]]; then
  if [ $RC -ne 0 ]; then echo "[ildsp] $MODE: FAIL を検出 (期待通り) rc=$RC"; exit 0; else echo "[ildsp] $MODE: *PASS してしまった* = ゲートが効いていない"; exit 1; fi
fi
exit $RC
