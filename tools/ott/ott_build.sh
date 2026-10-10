#!/usr/bin/env bash
# ott_build.sh: OTT lift→wasm 全鎖ビルド (m6 lift 産物 → m8 pass → m9 pass → ott pass → emcc)
#   入力 (読取専用): tools/m6/work/{ott_memfix1.ll, full_t1.drc.{dsm,ll}}, tools/m6/{msimd6.c,work/m6_*.c}, tools/m8,m9 の pass/rt
#   出力: tools/ott/work/ott.{ll,cjs,cjs.wasm}  (tools/m6..m10 には一切書かない)
#   OTT_VARIANT=<suffix> で IR pass 後の ll を差し替え可能 (開発用), OTT_PASSES で ott pass 集合を制御。
set -euo pipefail
OTT="$(cd -- "$(dirname -- "$0")" && pwd)"
T="$OTT/.."
M6="$T/m6"; M8="$T/m8"; M9="$T/m9"
W="$OTT/work"; mkdir -p "$W"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
cd "$M6"
for f in work/ott_memfix1.ll work/full_t1.drc.dsm work/full_t1.drc.ll msimd6.c work/m6_stubs.c work/m6_data.c; do
  [ -f "$f" ] || { echo "[ott_build] FATAL: $M6/$f 無し (tools/m6/m6_lift.sh + m6_build.sh の産物が必要)" >&2; exit 1; }
done
python3 "$M8/ir7_argpass_fixed.py" work/ott_memfix1.ll "$W/ott_argpass8.ll" \
  --dsm work/full_t1.drc.dsm --report "$W/argpass8_report.json" \
  --target function_180120af0 --tail function_18011de50 >/dev/null
python3 "$M8/ir8_valueflow.py" "$W/ott_argpass8.ll" "$W/ott_m8.ll" \
  --dsm work/full_t1.drc.dsm --full-ir work/full_t1.drc.ll --report "$W/valueflow_report.json" \
  --targets function_180126030 >/dev/null
python3 "$M9/ir9_bootstraps.py" "$W/ott_m8.ll" "$W/ott_m9.ll" --dsm work/full_t1.drc.dsm --report "$W/bootstraps_report.json" >/dev/null
python3 "$M9/ir9_outcopy.py" "$W/ott_m9.ll" "$W/ott_m9.ll" --report "$W/outcopy_report.json" >/dev/null
cp "$W/ott_m9.ll" "$W/ott_pre.ll"
# ott 独自 IR pass (OTT_PASSES= 空白区切りの passes/*.py。各 pass は `pass.py in.ll out.ll`)
IR="$W/ott_pre.ll"
for p in ${OTT_PASSES:-}; do
  python3 "$OTT/passes/$p.py" "$IR" "$W/ott_$p.ll"
  IR="$W/ott_$p.ll"
done
OUTN="${OTT_OUT:-ott}"
cp "$IR" "$W/$OUTN.ll"

EXPORTS=$(python3 - <<'PYEOF'
import re
src=open('m6_build.sh').read()
m=re.search(r'-sEXPORTED_FUNCTIONS=(\S+)', src)
print(m.group(1))
PYEOF
)
EXTRA_C=""
for c in ${OTT_EXTRA_C:-}; do EXTRA_C="$EXTRA_C $OTT/rt/$c"; done
emcc msimd6.c work/m6_stubs.c work/m6_data.c ../shim/src/heap.c ../shim/src/failfast.c "$OTT/rt/ott_rt.c" work/m6_stubs_hand.c work/m6_stubs_hand2.c \
  "$M8/m8_rt.c" "$M9/m9_rt.c" "$OTT/rt/ott_boot.c" $EXTRA_C \
  "$W/$OUTN.ll" \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAP32,HEAPF64 \
  -o "$W/$OUTN.cjs.tmp" \
  -w -Wno-error=int-conversion -Wno-implicit-function-declaration \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sEXPORTED_FUNCTIONS=$EXPORTS \
  -Wl,--no-gc-sections -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) 2>&1 | tee "$W/build_$OUTN.log" | tail -5
mv "$W/$OUTN.cjs.tmp" "$W/$OUTN.cjs"
[ -f "$W/$OUTN.cjs.tmp.wasm" ] && mv "$W/$OUTN.cjs.tmp.wasm" "$W/$OUTN.cjs.wasm" || true
echo "[ott_build] OK: $W/$OUTN.cjs"
