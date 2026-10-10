#!/usr/bin/env bash
# build_plugin_ott.sh — OTT (tools/m10 の lift 済み IR) + plugin_ott_entry.c を 1 module にビルド.
#   入力: tools/m10/work/ott_m10.ll (m10_build.sh の産物; 無ければ `bash tools/m10/m10_e2e.sh` で生成).
#         これを work/ に **コピー** して使い、tools/m6, m8, m9, m10 は読取のみ (改変 0).
#   出力: tools/hostbridge/work/ott_hb.cjs (+ .wasm)
set -euo pipefail
HB="$(cd -- "$(dirname -- "$0")/.." && pwd)"
T="$HB/.."
M6="$T/m6"; M8="$T/m8"; M9="$T/m9"; M10="$T/m10"
mkdir -p "$HB/work"

if [ ! -f "$HB/work/ott_m10.ll" ]; then
  [ -f "$M10/work/ott_m10.ll" ] || { echo "[build_plugin_ott] tools/m10/work/ott_m10.ll 無し: 先に bash tools/m10/m10_e2e.sh を実行" >&2; exit 1; }
  cp "$M10/work/ott_m10.ll" "$HB/work/ott_m10.ll"
fi
for f in "$M6/msimd6.c" "$M6/work/m6_stubs.c" "$M6/work/m6_data.c" "$M6/m6_rt.c" "$M6/work/m6_stubs_hand.c" \
         "$M6/work/m6_stubs_hand2.c" "$M8/m8_rt.c" "$M9/m9_rt.c" "$M10/m10_boot.c" "$T/shim/src/heap.c" "$T/shim/src/failfast.c"; do
  [ -f "$f" ] || { echo "[build_plugin_ott] 入力無し: $f" >&2; exit 1; }
done
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1

cd "$M6"   # m6/m10 と同じ cwd (相対 include 解決のため; 書込みは行わない)
EXPORTS=$(python3 - <<'PYEOF'
import re
src=open('m6_build.sh').read()
print(re.search(r'-sEXPORTED_FUNCTIONS=(\S+)', src).group(1))
PYEOF
)
STACK=8MB
GLOBAL_BASE=268435456
INITMEM="$((0x36000000))"

emcc "$M6/msimd6.c" "$M6/work/m6_stubs.c" "$M6/work/m6_data.c" "$T/shim/src/heap.c" "$T/shim/src/failfast.c" \
  "$M6/m6_rt.c" "$M6/work/m6_stubs_hand.c" "$M6/work/m6_stubs_hand2.c" \
  "$M8/m8_rt.c" "$M9/m9_rt.c" "$M10/m10_boot.c" \
  "$HB/poc/plugin_ott_entry.c" "$HB/work/ott_m10.ll" \
  --js-library "$HB/poc/hb_lib.js" -I "$HB/poc" \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -o "$HB/work/ott_hb.cjs.tmp" \
  -w -Wno-error=int-conversion -Wno-implicit-function-declaration \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=$STACK -sGLOBAL_BASE=$GLOBAL_BASE \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sEXPORTED_FUNCTIONS="$EXPORTS,_VSTPluginMain,_hb_icall,_hb_plugin_init,_hb_scratch" \
  -Wl,--no-gc-sections -Wl,--initial-memory=$INITMEM -Wl,--max-memory=$INITMEM 2>&1 | tail -5
mv "$HB/work/ott_hb.cjs.tmp" "$HB/work/ott_hb.cjs"
[ -f "$HB/work/ott_hb.cjs.tmp.wasm" ] && mv "$HB/work/ott_hb.cjs.tmp.wasm" "$HB/work/ott_hb.cjs.wasm"
ls -la "$HB/work/ott_hb.cjs" "$HB/work/ott_hb.cjs.wasm"
echo "[build_plugin_ott] OK"
