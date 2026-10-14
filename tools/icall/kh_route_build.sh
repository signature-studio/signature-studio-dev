#!/usr/bin/env bash
# kh_route_build.sh — Kilohearts Gain (HeartCore closure, icall 経路) の復元後 IR → wasm ビルド (ICALL-17 #1025)。
#   入力: work/rt_kilohearts-gain/after.0.restored.ll (rewrite + RetDec decode-only 済み。ICALL-12 #853 の成果物)
#   出力: work/kh_route/kh_route.{cjs,wasm}
#   範囲: 復元後 IR → fix_mask/fix_vstore → normalize/ir5 → flatten → SIMD/VEX helper → emcc。
#   未了: PE data 敷設 (ott_data_install は空)・差分実行 (native 比較) は本スクリプトに含まれない。
#         前回 run で wasm 実行は 61/61 シナリオが memory access out of bounds で trap (#1025 コメント参照)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T="$HERE/.."
SRC="$HERE/work/rt_kilohearts-gain/after.0.restored.ll"
W="$HERE/work/kh_route"; mkdir -p "$W/tmp"
M11="$(cd -- "$T/m11" && pwd)"
if [ ! -f "$SRC" ]; then echo "[kh_route] $SRC が無い: 素材 work-icall を展開し、rewrite+RetDec を先に実行" >&2; exit 2; fi
MAP="$HERE/work/rt_kilohearts-gain/map.json"
if [ ! -f "$MAP" ]; then echo "[kh_route] $MAP が無い: icall_rewrite.py の出力 (blk / cfg_thunks) が必要" >&2; exit 2; fi
BLK="$(python3 -c "import json,sys;print(hex(json.load(open(sys.argv[1]))['blk'] - 0x150000000))" "$MAP")"
CFG="$(python3 -c "import json,sys;print(','.join('%x' % v for v in json.load(open(sys.argv[1]))['cfg_thunks']))" "$MAP")"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
# 1. 復元後 IR の後処理 (fix_mask / fix_vstore を無条件に実行)
python3 "$HERE/ir_fix_mask.py" "$SRC" "$W/oi.restored.ll" | tee "$W/fix_mask.json"
python3 "$HERE/ir_fix_vstore.py" "$W/oi.restored.ll" "$W/oi.restored1.ll" --direct | tee "$W/fix_vstore.json"; mv "$W/oi.restored1.ll" "$W/oi.restored.ll"
# 2. 既存 pass (normalize / ir5_patch) → flatten (global→絶対 addr + shift + dispatch 表)
python3 "$T/m2/ir_normalize.py" "$W/oi.restored.ll" "$W/oi.norm0.ll" >/dev/null
python3 "$T/m5/ir5_patch.py" "$W/oi.norm0.ll" "$W/oi.lift.ll" --report "$W/ir5.json" >/dev/null 2>&1
cp "$W/oi.lift.ll" "$W/oi.p1.ll"
python3 "$HERE/ir_flatten.py" "$W/oi.p1.ll" "$W/oi.flat.ll" --limit 0x0c000000 --table "$W/oi.table.c" --cfg "$CFG"
# 3. SIMD / VEX helper (silent 0 返却を残さない)
python3 "$T/m11/m11_simd2.py" "$W/oi.flat.ll" 2> "$W/simd.log" > "$W/oi.simd0.c"
sed -i "s#\"../msimd11_core.h\"#\"$M11/msimd11_core.h\"#; s#\"../m11/msimd11_core.h\"#\"$M11/msimd11_core.h\"#" "$W/oi.simd0.c"
python3 "$HERE/vex_gen.py" "$W/oi.flat.ll" "$W/oi.vex.c" | tee "$W/vex_gen.json"
python3 "$HERE/simd_merge.py" "$W/oi.simd0.c" "$W/oi.simd.c" "$HERE/rt/icall_simd_extra.c" "$W/oi.vex.c" --report "$W/simd_merge.json"
# 4. PE data 敷設 (.rdata/.data/_RDATA を 0x30000000+RVA へ。data_gen.py は OTT と同じ規約)
PE="$HERE/work/kh_pe/HeartCore.core_64"
if [ ! -f "$PE" ]; then echo "[kh_route] $PE が無い: plugins-kilohearts の windows.zip から HeartCore.core_64 を展開" >&2; exit 2; fi
python3 "$T/ott/lift/data_gen.py" "$PE" "$W/kh_data.c"
# 5. build (BLK は map.json の blk、メモリ量は 0x3c000000 固定)
emcc "$W/oi.flat.ll" "$W/oi.simd.c" "$W/oi.vex.c" "$W/oi.table.c" "$HERE/rt/icall_rt.c" "$HERE/rt/icall_ovr.c" "$HERE/rt/icall_simd_extra.c" "$W/kh_data.c" \
  -DICALL_BLK=$BLK -w -O0 -g -ffp-contract=off -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 -sERROR_ON_UNDEFINED_SYMBOLS=0 \
  -sEXPORTED_FUNCTIONS=_ott_run,_ott_xmm0,_ott_data_install,_malloc -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x3c000000)) -Wl,--max-memory=$((0x3c000000)) -o "$W/kh_route.cjs" 2> "$W/emcc.log" || { grep -v 'warning' "$W/emcc.log" | head; exit 1; }
ls -la "$W/kh_route.cjs" "$W/kh_route.wasm"
echo "[kh_route] OK: $W/kh_route.cjs (build のみ。実行差分は未了)"
