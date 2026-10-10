#!/usr/bin/env bash
# gain::GainDsp::process (SlateCore.core_64 0x180afe090) lift → wasm → 実機 x86 bit-exact 照合 (1 コマンド E2E)
#   usage: bash tools/targets/freshair/lift/gain_e2e.sh [N=400]
# 前提: work/win/ にインストーラ展開済み (../fetch.sh)。出力: work/lift_gain/
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$(dirname "$HERE")"
CORE="$FA/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
W="$FA/work/lift_gain"; mkdir -p "$W/tmp"; cd "$W"
N="${1:-400}"
export TMPDIR="$W/tmp"
echo "[1] RetDec (select-ranges: process + 2 meter setter)"
/opt/retdec/bin/retdec-decompiler "$CORE" -o gain.drc.c \
  --select-ranges "0x180afe090-0x180afe24e,0x180afe3a0-0x180afe415,0x180afe420-0x180afe495" --select-decode-only --timeout 900 > gain.retdec.log 2>&1
rm -f gain.drc.dsm
echo "[2] normalize + ir5_patch (m2/m5 参照コピー)"
python3 "$FA/ref/ir_normalize.py" gain.drc.ll gain_norm0.ll >/dev/null
python3 "$FA/ref/ir5_patch.py" gain_norm0.ll gain_lift.ll --report ir5_report.json >/dev/null 2>&1
echo "[3] FA 修復 pass (P1' comisd 分岐 / F7' deref / F2' xmm1 引数)"
python3 "$HERE/fa_fix_gain.py" gain_lift.ll gain_fixed.ll
echo "[4] emcc → wasm"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc -w -O1 -ffp-contract=off -frounding-math -fno-fast-math gain_fixed.ll "$HERE/fa_simd.c" "$HERE/fa_stub.c" \
  -sERROR_ON_UNDEFINED_SYMBOLS=1 -sMODULARIZE=1 -sENVIRONMENT=node -sALLOW_MEMORY_GROWTH=1 \
  -sEXPORTED_FUNCTIONS=_malloc,_free,_function_180afe090 -sEXPORTED_RUNTIME_METHODS=HEAPU8 --no-entry -Wl,--no-gc-sections -o gain.js
mv gain.js gain.cjs
echo "[5] native 参照 (実機機械語を ImageBase に敷設して ms_abi 直接実行)"
cc -O1 -o native_gain "$HERE/native_gain.c"
python3 "$HERE/gen_scen.py" scen.txt "$N"
./native_gain "$CORE" scen.txt > out_native.txt
node "$HERE/gain_harness.mjs" ./gain.cjs scen.txt > out_wasm.txt
echo "[6] 照合"
if cmp -s out_native.txt out_wasm.txt; then echo "RESULT: BIT-EXACT $(wc -l < out_native.txt)/$N scenarios"; else
  awk 'NR==FNR{a[FNR]=$0;next}{if(a[FNR]!=$0)c++}END{print "RESULT: MISMATCH lines:",c+0}' out_native.txt out_wasm.txt; exit 1; fi
# 修復なし(ir5_patch のみ)版の不一致数 (対照): P1'/F7'/F2' が必要であることの実測
