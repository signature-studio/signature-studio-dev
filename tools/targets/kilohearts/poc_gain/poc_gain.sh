#!/usr/bin/env bash
# kHs Gain PoC: HeartCore.core_64 gain::GainDsp::process (0x1804b0380, 609B) lift → wasm → 実機 x86 と bit 突合
# 再実行: bash tools/targets/kilohearts/poc_gain/poc_gain.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
mkdir -p work/tmp
CORE="${CORE:-$HERE/../work/winpkg/HeartCore.core_64}"
[ -f "$CORE" ] || { echo "HeartCore.core_64 が無い: bash ../scripts/extract_installer.sh を先に実行" >&2; exit 2; }
export TMPDIR="$HERE/work/tmp"

echo "[1/6] native 参照 (実機機械語を ImageBase 0x180000000 に VA 敷設して ms_abi 直接実行)"
cc -O1 -o work/native_ref native_ref.c
./work/native_ref "$CORE" work/vectors.json

echo "[2/6] RetDec lift (--select-ranges 0x1804b0380-0x1804b05e1, 全 PE 入力)"
if [ ! -f work/gain.drc.ll ]; then
  /opt/retdec/bin/retdec-decompiler "$CORE" -o work/gain.drc.c \
    --select-ranges 0x1804b0380-0x1804b05e1 --select-decode-only --timeout 1200 > work/gain.retdec.log 2>&1
  rm -f work/gain.drc.dsm
fi
echo "      gain.drc.ll: $(wc -l < work/gain.drc.ll) 行"

echo "[3/6] IR pass 鎖: normalize(m2) → ir5_patch(m5 継承) → kh_p1(ucomisd flag 修復) → kh_f7(ch0 deref 復元)"
python3 ref/ir_normalize.py work/gain.drc.ll work/gain_norm0.ll >/dev/null
python3 ref/ir5_patch.py work/gain_norm0.ll work/gain_lift.ll --report work/ir5_report.json 2>&1 | grep -E "R1|S1a" || true
python3 ir_kh_p1.py work/gain_lift.ll work/gain_p1.ll
python3 ir_kh_f7.py work/gain_p1.ll work/gain_f7.ll

echo "[4/6] emcc → wasm"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc -w -O1 -msimd128 -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=64MB -sENVIRONMENT=node \
  -sMODULARIZE=1 -sEXPORT_NAME=KhGain -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry \
  -sEXPORTED_FUNCTIONS=_function_1804b0380,_malloc,_free -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32 \
  -Wl,--no-gc-sections \
  work/gain_f7.ll kh_simd_gain.c -o work/kh_gain.cjs
ls -la work/kh_gain.wasm

echo "[5/6] wasm vs native bit 突合"
node poc_gain_compare.mjs work/vectors.json work/kh_gain.cjs
echo "[6/6] DONE"
