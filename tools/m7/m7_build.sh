#!/usr/bin/env bash
# m7_build.sh (M7 PoC): m6 ビルド鎖 + ir7_argpass (f32 引数接続) を挿した再検証ビルド.
#   tools/m6 側スクリプトは読取のみ (改変なし)。診断物は tools/m7/work/ に置く。
#   work 直下再生成物 (ott_memfix*.ll / ott_argpass.ll) は m6 と同一の手続で
#   再生成する (work/ は commit 対象外の scratch)。
# EMCC 引数は m6_build.sh と同一 (**EXPORTED_FUNCTIONS も手元再出力で一致**)、
# 入力 IR のみ差替 (ir7_argpass.py 挿入)。出力を tools/m7/work/ に分離。
set -euo pipefail
M6="$(cd -- "$(dirname -- "$0")" && pwd)/../m6"
M7="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$M6"
source ../m1/flags.sh 2>/dev/null || true
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
mkdir -p "$M7/work"

MSIMD_SRC=msimd6.c
if [ ! -f "$MSIMD_SRC" ]; then
  echo "[m7_build] FATAL: msimd6.c 未生成" >&2
  exit 1
fi

if [ ! -f work/ott_shift3b.ll ]; then
  echo "[m7_build] ott_lift / ir6 chain が無い → 生成 (m6_lift.sh + ir6 3 pass)" >&2
  bash m6_lift.sh
  python3 ir6_pass.py  work/ott_lift.ll  work/ott_shift.ll
  python3 ir6_shift.py work/ott_shift.ll work/ott_shift2.ll
  python3 ir6_gdata.py work/ott_shift2.ll work/ott_shift3b.ll
fi
if [ ! -f work/ott_memfix0.ll ]; then
  python3 m6_memfix.py work/ott_shift3b.ll work/ott_memfix0.ll
fi
if [ ! -f work/ott_memfix1.ll ]; then
  # m6_full_extract.py は work/ott_memfix0.ll を読み argv[1] へ splice
  python3 m6_full_extract.py work/ott_memfix1.ll function_1801260c0 function_180126030 function_180126010
fi
# ir7 argpass PoC (tools/m7): f32 bits を 3rd arg 化 + setParameter 本体再生成
python3 "$M7/ir7_argpass.py" work/ott_memfix1.ll work/ott_argpass.ll \
  --dsm work/full_t1.drc.dsm --report "$M7/work/argpass_report.json" \
  --target function_180120af0 --tail function_18011de50

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
  work/ott_argpass.ll \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAP32,HEAPF64 \
  -o "$M7/work/ott_argpass.cjs.tmp" \
  -w -Wno-error=int-conversion -Wno-implicit-function-declaration \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=$STACK -sGLOBAL_BASE=$GLOBAL_BASE \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sEXPORTED_FUNCTIONS=$EXPORTS \
  -Wl,--no-gc-sections \
  -Wl,--initial-memory=$INITMEM \
  -Wl,--max-memory=$MAXMEM 2>&1 | tee "$M7/work/build_argpass.log" | tail -3
mv "$M7/work/ott_argpass.cjs.tmp" "$M7/work/ott_argpass.cjs"
echo "[m7_build] OK: m7/work/ott_argpass.cjs (+ .wasm)"
