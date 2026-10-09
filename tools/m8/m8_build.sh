#!/usr/bin/env bash
# m8_build.sh (M8): m7_build.sh の鎖に ir7_argpass_fixed (idx_store32 正本差分) +
# ir8_valueflow (pattern C 係数群 value-flow 接続) + m8_rt.c (missing 10 stub) を
# 追加した build。tools/m6 側スクリプトは読取のみ (改変なし)。診断物は tools/m8/work/。
set -euo pipefail
M6="$(cd -- "$(dirname -- "$0")" && pwd)/../m6"
M8="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$M6"
source ../m1/flags.sh 2>/dev/null || true
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
mkdir -p "$M8/work"

MSIMD_SRC=msimd6.c
if [ ! -f "$MSIMD_SRC" ]; then
  echo "[m8_build] FATAL: msimd6.c 未生成" >&2
  exit 1
fi

if [ ! -f work/ott_shift3b.ll ]; then
  echo "[m8_build] ott_lift / ir6 chain が無い → 生成 (m6_lift.sh + ir6 3 pass)" >&2
  bash m6_lift.sh
  python3 ir6_pass.py  work/ott_lift.ll  work/ott_shift8a.ll
  python3 ir6_shift.py work/ott_shift8a.ll work/ott_shift8b.ll
  python3 ir6_gdata.py work/ott_shift8b.ll work/ott_shift8.ll
fi
if [ ! -f work/ott_memfix0.ll ]; then
  python3 m6_memfix.py work/ott_shift3b.ll work/ott_memfix0.ll
fi
if [ ! -f work/ott_memfix1.ll ]; then
  # m6_full_extract.py は work/ott_memfix0.ll を読み argv[1] へ splice
  python3 m6_full_extract.py work/ott_memfix1.ll function_1801260c0 function_180126030 function_180126010
fi
# ir7_argpass_fixed (tools/m8): idx_store32 disp ずれ修正 + f32 bits 3rd arg 化
python3 "$M8/ir7_argpass_fixed.py" work/ott_memfix1.ll "$M8/work/ott_argpass8.ll" \
  --dsm work/full_t1.drc.dsm --report "$M8/work/argpass8_report.json" \
  --target function_180120af0 --tail function_18011de50
# ir8_valueflow (tools/m8): pattern C 係数群 value-flow 接続 (arg-trunc 誤訳の再生成)
python3 "$M8/ir8_valueflow.py" "$M8/work/ott_argpass8.ll" "$M8/work/ott_m8.ll" \
  --dsm work/full_t1.drc.dsm --full-ir work/full_t1.drc.ll --report "$M8/work/valueflow_report.json" \
  --targets function_180126030

STACK=8MB
GLOBAL_BASE=268435456
INITMEM="$((0x36000000))"
MAXMEM="$((0x36000000))"

EXPORTS=$(python3 - <<'PYEOF'
import re
src=open('m6_build.sh').read()
m=re.search(r'-sEXPORTED_FUNCTIONS=(\S+)', src)
print(m.group(1))
PYEOF
)

emcc $MSIMD_SRC work/m6_stubs.c work/m6_data.c ../shim/src/heap.c ../shim/src/failfast.c m6_rt.c work/m6_stubs_hand.c work/m6_stubs_hand2.c \
  "$M8/m8_rt.c" \
  "$M8/work/ott_m8.ll" \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAP32,HEAPF64 \
  -o "$M8/work/ott_m8.cjs.tmp" \
  -w -Wno-error=int-conversion -Wno-implicit-function-declaration \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=$STACK -sGLOBAL_BASE=$GLOBAL_BASE \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sEXPORTED_FUNCTIONS=$EXPORTS \
  -Wl,--no-gc-sections \
  -Wl,--initial-memory=$INITMEM \
  -Wl,--max-memory=$MAXMEM 2>&1 | tee "$M8/work/build_m8_full.log" | tail -3
mv "$M8/work/ott_m8.cjs.tmp" "$M8/work/ott_m8.cjs"
echo "[m8_build] OK: m8/work/ott_m8.cjs (+ .wasm)"
