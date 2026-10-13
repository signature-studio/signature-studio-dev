#!/usr/bin/env bash
# win Reverb.dll (x64) の Process_Fruity_32FM_32FS / Process_UF_32FM_32FS lift + native 実機械語との差分テスト。
#   locate (export stub -> .pdata) -> RetDec --select-ranges -> ir_normalize -> fix_rv ([D] ucomiss) -> gen_helpers -> emcc -> diff_test
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/libreverb/lift.sh [ok|neg-helper|neg-nofix|neg-compare|neg-nan|all]
#   ok (既定) : 本検査。全ケース一致で exit 0、1 ケースでも不一致なら非 0。
#   neg-helper(mulss→add) / neg-nofix(ucomiss 修復無し) / neg-compare(比較器: wasm 結果 1bit 反転) / neg-nan(oeq→ueq)
#   neg-*     : ネガティブコントロール。 *FAIL する* ことを確認し、FAIL した時に exit 0 / 通ってしまった時に exit 1。
#   all       : ok + 全 neg-* (いずれか期待外れなら非 0)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
source "$ROOT/env.sh"
MODE="${1:-ok}"
if [ "$MODE" = all ]; then
  for m in ok neg-helper neg-nofix neg-compare neg-nan; do bash "$0" "$m" || exit 1; done; echo "[rv] ALL OK (本検査 PASS + ネガコン 4 件が期待通り FAIL)"; exit 0
fi
DLL="${REVERB_DLL:-$FL_WIN64_DIR/extracted/block24352_PE.bin}"
[ -f "$DLL" ] || { echo "[rv] Reverb.dll not found: $DLL (FL_WIN64_DIR=$FL_WIN64_DIR)"; exit 2; }
W="$ROOT/work/lift/libreverb/$MODE"; mkdir -p "$W"
EMSDK="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"; RETDEC="${RETDEC_BIN:-/opt/retdec/bin/retdec-decompiler}"
source "$EMSDK" >/dev/null 2>&1
cp "$DLL" "$W/Reverb.dll"
python3 "$HERE/locate.py" "$W/Reverb.dll" "$W/loc"
RANGES=$(python3 -c "import json;r=json.load(open('$W/loc/ranges.json'));print(r['fruity']['range']+','+r['uf']['range'])")
"$RETDEC" "$W/Reverb.dll" -o "$W/rv.drc.c" --select-ranges "$RANGES" --select-decode-only --timeout 600 > "$W/rv.retdec.log" 2>&1
echo "[rv] retdec: $(grep -c '^define' "$W/rv.drc.ll") functions lifted (ranges $RANGES)"
python3 "$HERE/../libkio/ir_normalize.py" "$W/rv.drc.ll" "$W/rv_norm_raw.ll" >/dev/null
if [ "$MODE" = neg-nofix ]; then cp "$W/rv_norm_raw.ll" "$W/rv_norm.ll"; else python3 "$HERE/fix_rv.py" "$W/rv_norm_raw.ll" "$W/rv_norm.ll" 2; fi
# neg-nan: ucomiss 修復の fcmp oeq (NaN で false) を ueq (NaN で true) に誤らせる = jp 経路の検査が効いているかの確認
if [ "$MODE" = neg-nan ]; then sed -i 's/fcmp oeq float/fcmp ueq float/' "$W/rv_norm.ll"; [ "$(grep -c 'fcmp ueq' "$W/rv_norm.ll")" = 2 ]; fi
BRK=(); [ "$MODE" = neg-helper ] && BRK=(--break mulss)
python3 "$HERE/gen_helpers.py" "$W/rv_norm.ll" "$W/rv_simd.c" "${BRK[@]}"
F1=$(python3 -c "import json;print('function_%x'%(json.load(open('$W/loc/ranges.json'))['image_base']+json.load(open('$W/loc/ranges.json'))['fruity']['begin']))")
F2=$(python3 -c "import json;print('function_%x'%(json.load(open('$W/loc/ranges.json'))['image_base']+json.load(open('$W/loc/ranges.json'))['uf']['begin']))")
[ "$F1" = function_180001240 ] && [ "$F2" = function_180001ba0 ] || { echo "[rv] unexpected lifted names $F1 $F2 (run_wasm.mjs は固定名)"; exit 2; }
emcc "$W/rv_norm.ll" "$W/rv_simd.c" -o "$W/rv.wasm" -O1 -w -sSTANDALONE_WASM=1 -sERROR_ON_UNDEFINED_SYMBOLS=0 -sALLOW_MEMORY_GROWTH=0 \
  -sINITIAL_MEMORY=16MB -sSTACK_SIZE=256KB -sGLOBAL_BASE=1024 --no-entry -Wl,--no-gc-sections -Wl,--export=$F1 -Wl,--export=$F2
echo "[rv] wasm: $(stat -c %s "$W/rv.wasm") bytes"
ARGS=(); [ "$MODE" = neg-compare ] && ARGS=(--mutate-wasm-result)
set +e; python3 "$HERE/diff_test.py" "$W" "${ARGS[@]}"; RC=$?; set -e
if [[ "$MODE" == neg-* ]]; then
  if [ $RC -ne 0 ]; then echo "[rv] $MODE: FAIL を検出 (期待通り) rc=$RC"; exit 0; else echo "[rv] $MODE: *PASS してしまった* = ゲートが効いていない"; exit 1; fi
fi
exit $RC
