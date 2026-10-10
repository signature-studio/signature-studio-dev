#!/usr/bin/env bash
# m10_build.sh (M10): m9_build.sh の m10 版 — C 側 band filter port を tools/m10/m10_boot.c に入替。
# tools/m6 / tools/m8 / tools/m9 は読取のみ (改変しない)。産物は tools/m10/work/ 配下。
set -euo pipefail
M6="$(cd -- "$(dirname -- "$0")" && pwd)/../m6"
M8="$(cd -- "$(dirname -- "$0")" && pwd)/../m8"
M9="$(cd -- "$(dirname -- "$0")" && pwd)/../m9"
M10="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$M6"
source ../m1/flags.sh 2>/dev/null || true
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
mkdir -p "$M10/work"

MSIMD_SRC=msimd6.c
if [ ! -f "$MSIMD_SRC" ]; then
  echo "[m10_build] FATAL: msimd6.c 未生成" >&2
  exit 1
fi

if [ ! -f work/ott_shift3b.ll ]; then
  echo "[m10_build] ott_lift / ir6 chain 無し → 生成" >&2
  bash m6_lift.sh
  python3 ir6_pass.py  work/ott_lift.ll  work/ott_shift8a.ll
  python3 ir6_shift.py work/ott_shift8a.ll work/ott_shift8b.ll
  python3 ir6_gdata.py work/ott_shift8b.ll work/ott_shift8.ll
fi
if [ ! -f work/ott_memfix0.ll ]; then
  python3 m6_memfix.py work/ott_shift3b.ll work/ott_memfix0.ll
fi
if [ ! -f work/ott_memfix1.ll ]; then
  python3 m6_full_extract.py work/ott_memfix1.ll function_1801260c0 function_180126030 function_180126010
fi
# m8 鎖 (tools/m8/work 産物が既に在れば reuse)
python3 "$M8/ir7_argpass_fixed.py" work/ott_memfix1.ll "$M8/work/ott_argpass8.ll" \
  --dsm work/full_t1.drc.dsm --report "$M8/work/argpass8_report.json" \
  --target function_180120af0 --tail function_18011de50
python3 "$M8/ir8_valueflow.py" "$M8/work/ott_argpass8.ll" "$M8/work/ott_m8.ll" \
  --dsm work/full_t1.drc.dsm --full-ir work/full_t1.drc.ll --report "$M8/work/valueflow_report.json" \
  --targets function_180126030
# m9 IR pass たち (参照 copy: tools/m9 スクリプトを直接実行して m10/work 配下へ出力)
python3 "$M9/ir9_bootstraps.py" "$M8/work/ott_m8.ll" "$M10/work/ott_m10.ll" \
  --dsm work/full_t1.drc.dsm --report "$M10/work/bootstraps_m10.json"
python3 "$M9/ir9_outcopy.py" "$M10/work/ott_m10.ll" "$M10/work/ott_m10.ll" \
  --report "$M10/work/outcopy_m10.json"

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
  "$M8/m8_rt.c" "$M9/m9_rt.c" "$M10/m10_boot.c" \
  "$M10/work/ott_m10.ll" \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -o "$M10/work/ott_m10.cjs.tmp" \
  -w -Wno-error=int-conversion -Wno-implicit-function-declaration \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=$STACK -sGLOBAL_BASE=$GLOBAL_BASE \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sEXPORTED_FUNCTIONS=$EXPORTS \
  -Wl,--no-gc-sections \
  -Wl,--initial-memory=$INITMEM \
  -Wl,--max-memory=$MAXMEM 2>&1 | tee "$M10/work/build_m10.log" | tail -5
mv "$M10/work/ott_m10.cjs.tmp" "$M10/work/ott_m10.cjs"
echo "[m10_build] OK: m10/work/ott_m10.cjs (+ .wasm)"
