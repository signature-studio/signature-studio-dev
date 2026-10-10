#!/usr/bin/env bash
# build_m10_lb.sh — hostbridge の OTT module (tools/m10 の RetDec lift + plugin_ott_entry.c surrogate) を低位 base・小 memory で再ビルド.
#   入力は tools/m10/work/ott_m10.ll (m10_e2e.sh の産物) と tools/m6,m8,m9,m10,shim,hostbridge/poc の既存ソース (全て読取のみ).
#   これらを work/ へ「リテラル再配置コピー」して emcc に渡す (lb_reloc.py). 本体 pass 鎖 (ir6_shift 等) は無改変で再実行不要.
#   env: LB_BASE(0x10000) LB_INIT_MIB(24) LB_MAX_MIB(64) LB_PREFIX('') LB_OUT LB_NAME(ott_hb)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; LB="$HERE/.."; T="$LB/../.."
M6="$T/m6"; M8="$T/m8"; M9="$T/m9"; M10="$T/m10"; HB="$T/hostbridge"; DLL=/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll
LB_BASE="${LB_BASE:-0x10000}"; LB_INIT_MIB="${LB_INIT_MIB:-24}"; LB_MAX_MIB="${LB_MAX_MIB:-64}"; LB_PREFIX="${LB_PREFIX:-}"
OUT="${LB_OUT:-$LB/work/m10_$LB_BASE}"; NAME="${LB_NAME:-ott_hb}"; SRC="$OUT/src"
mkdir -p "$SRC"
[ -f "$M10/work/ott_m10.ll" ] || { echo "[build_m10_lb] $M10/work/ott_m10.ll 無し: 先に bash tools/m10/m10_e2e.sh" >&2; exit 1; }
python3 "$LB/lb_layout.py" --base "$LB_BASE" --arena-size 0x120000 --init-mib "$LB_INIT_MIB" --max-mib "$LB_MAX_MIB" ${LB_X_ARENA:+--no-check} > "$OUT/layout.sh"
source "$OUT/layout.sh"
# 診断用: レイアウト個別上書き (LB_X_ARENA / LB_X_GB / LB_X_INIT_MIB: 切り分け実験で image base と heap/arena 位置を独立に動かす)
LB_ARENA=${LB_X_ARENA:-$LB_ARENA}; LB_GLOBAL_BASE=${LB_X_GB:-$LB_GLOBAL_BASE}; [ -n "${LB_X_INIT_MIB:-}" ] && { LB_INIT=$((LB_X_INIT_MIB<<20)); LB_INIT_MIB=$LB_X_INIT_MIB; }
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
R="python3 $HERE/lb_reloc.py"; P=${LB_PREFIX:+--prefix $LB_PREFIX}
$R ll "$M10/work/ott_m10.ll" "$OUT/ott_m10.ll" --new "$LB_BASE" $P --report "$OUT/reloc_ll.json"
for f in "$M6/msimd6.c" "$M6/work/m6_stubs.c" "$M6/m6_rt.c" "$M6/work/m6_stubs_hand.c" "$M6/work/m6_stubs_hand2.c" "$M8/m8_rt.c" "$M9/m9_rt.c" "$M10/m10_boot.c" "$T/shim/src/heap.c" "$T/shim/src/failfast.c" "$HB/poc/plugin_ott_entry.c"; do
  b=$(basename "$f"); [ -f "$f" ] || { echo "入力無し: $f" >&2; exit 1; }
  $R c "$f" "$SRC/$b" --new "$LB_BASE" --maxmem "$LB_MAX" $P --report "$OUT/reloc_$b.json" | tail -1
done
sed -i 's/#define HB_ARENA 0x30400000u/#define HB_ARENA LB_ARENA_ADDR/' "$SRC/plugin_ott_entry.c"
grep -q 'HB_ARENA LB_ARENA_ADDR' "$SRC/plugin_ott_entry.c" || { echo "plugin_ott_entry.c: HB_ARENA 定義が変わった (要追従)" >&2; exit 1; }
python3 "$LB/x64c/lb_data_gen.py" "$DLL" "$SRC/m6_data.c" - "$LB_BASE" --m6 | tail -1
EXPORTS=$(python3 - <<'PYEOF'
import re
src=open('m6_build.sh').read() if False else open('/home/ubuntu/work/webstudio/tools/m6/m6_build.sh').read()
print(re.search(r'-sEXPORTED_FUNCTIONS=(\S+)', src).group(1))
PYEOF
)
[ -n "$LB_PREFIX" ] && EXPORTS=$(python3 "$HERE/lb_reloc.py" exports "$EXPORTS" --prefix "$LB_PREFIX")
cd "$M6"   # 相対 include 解決のため m6 と同 cwd (書込みは行わない)
emcc "$SRC/msimd6.c" "$SRC/m6_stubs.c" "$SRC/m6_data.c" "$SRC/heap.c" "$SRC/failfast.c" \
  "$SRC/m6_rt.c" "$SRC/m6_stubs_hand.c" "$SRC/m6_stubs_hand2.c" "$SRC/m8_rt.c" "$SRC/m9_rt.c" "$SRC/m10_boot.c" \
  "$SRC/plugin_ott_entry.c" "$OUT/ott_m10.ll" \
  --js-library "$HB/poc/hb_lib.js" -I "$HB/poc" -I "$M6" -I "$M6/work" -I "$T/shim/src" -DLB_ARENA_ADDR=${LB_ARENA}u \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -o "$OUT/$NAME.tmp.cjs" \
  -w -Wno-error=int-conversion -Wno-implicit-function-declaration \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=$LB_GLOBAL_BASE \
  -sENVIRONMENT=node,web,worker -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sEXPORTED_FUNCTIONS="$EXPORTS,_VSTPluginMain,_hb_icall,_hb_plugin_init,_hb_scratch" \
  -Wl,--no-gc-sections -sINITIAL_MEMORY=$LB_INIT -sMAXIMUM_MEMORY=$LB_MAX 2>&1 | tail -5
mv "$OUT/$NAME.tmp.cjs" "$OUT/$NAME.cjs"; mv "$OUT/$NAME.tmp.wasm" "$OUT/$NAME.wasm"
sed -i "s/$NAME.tmp.wasm/$NAME.wasm/g" "$OUT/$NAME.cjs"
echo "[build_m10_lb] OK: $OUT/$NAME.cjs (base=$LB_BASE arena=0x$(printf %x $LB_ARENA) gb=0x$(printf %x $LB_GLOBAL_BASE) init=${LB_INIT_MIB}MiB max=${LB_MAX_MIB}MiB)"
