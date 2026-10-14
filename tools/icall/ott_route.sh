#!/usr/bin/env bash
# ott_route.sh — OTT を「RetDec ルート + 間接 call 復元 pass」で wasm 化する (x64c.py 非使用)。
#   closure(F) → icall_rewrite(PE 書換え) → RetDec(decode-only) → ir_icall_restore → normalize/ir5_patch → ir_flatten → emcc
#   出力: work/route/ott_route.{cjs,wasm}  (tools/ott/diff/matrix.py 互換: _ott_run/_ott_data_install)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T="$HERE/.."
W="$HERE/work/route"; mkdir -p "$W/tmp"
OTT_DLL="${ANALYSIS_DIR:-/home/ubuntu/work/analysis}/plugins/ott/binaries/OTT_vst2_win64.dll"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
# 1. F = 実行された関数 (x64c native coverage = lift_meta) + RetDec closure(m6) の直接 call/tail-jmp 推移閉包
if [ ! -f "$T/ott/work/lift/lift_meta.json" ]; then echo "[route] tools/ott/work/lift/lift_meta.json が無い: bash tools/ott/ott_e2e.sh を先に実行" >&2; exit 2; fi
python3 - "$T" "$W" <<'PY'
import json, sys
T, W = sys.argv[1:3]
m = json.load(open(T + '/ott/work/lift/lift_meta.json'))
r = open(T + '/m6/work/ott_ranges.txt').read().strip()
import os
extra = [x for x in os.environ.get('ICALL_EXTRA_ROOTS', '1801c8cb8').split(',') if x]   # 実行されないが override 対象の CRT 関数 (_handle_errorf)
open(W + '/roots.txt', 'w').write(r + ',' + ','.join('0x' + f for f in m['functions'] + extra))
PY
python3 "$HERE/closure.py" --pe "$OTT_DLL" --roots "$W/roots.txt" --out "$W/F.txt"
# 2. PE 書換え (間接 call/jmp → memory-ABI + stub, [reg] deref 補償, closure 内 ABI 仮想化)
python3 "$HERE/icall_rewrite.py" --pe "$OTT_DLL" --funcs "$W/F.txt" --out "$W/ott_icall.dll" --map "$W/map.json"
python3 - "$W" <<'PY'
import json, sys
W = sys.argv[1]
m = json.load(open(W + '/map.json'))
open(W + '/ranges.txt', 'w').write(open(W + '/map.json.ranges').read() + ',0x%x-0x%x,0x%x-0x%x' % (m['stub'], m['stub'] + m.get('stub_len', 78), m['comis_stub'], m['comis_stub'] + m.get('comis_stub_len', 29)))
PY
# 3. RetDec decode-only
( cd "$W" && TMPDIR="$W/tmp" /opt/retdec/bin/retdec-decompiler ott_icall.dll -o oi.drc.c --select-ranges "$(cat ranges.txt)" --select-decode-only --timeout 2400 > retdec.log 2>&1 )
# 4. 復元 (new→orig VA, stub → __icall_dispatch)
python3 "$HERE/ir_icall_restore.py" --ir "$W/oi.drc.ll" --map "$W/map.json" --out "$W/oi.restored0.ll" --report "$W/restore.json"
if [ "${ICALL_FIX_MASK:-1}" = "1" ]; then python3 "$HERE/ir_fix_mask.py" "$W/oi.restored0.ll" "$W/oi.restored.ll" | tee "$W/fix_mask.json"
else cp "$W/oi.restored0.ll" "$W/oi.restored.ll"; echo '{"hi32_mask_fixed": "skipped (negative control)"}' | tee "$W/fix_mask.json"; fi
# RetDec が xmm→stack の vmovapd store を void helper に落とした箇所を store に戻す (N3, ICALL_FIX_VSTORE=0 でネガコン)
if [ "${ICALL_FIX_VSTORE:-1}" = "1" ]; then python3 "$HERE/ir_fix_vstore.py" "$W/oi.restored.ll" "$W/oi.restored1.ll" | tee "$W/fix_vstore.json"; mv "$W/oi.restored1.ll" "$W/oi.restored.ll"
else echo '{"vstore_fixed": "skipped (negative control)"}' | tee "$W/fix_vstore.json"; fi
# 5. 既存 pass (normalize / ir5_patch) → flatten (global→絶対 addr + shift + dispatch 表)
python3 "$T/m2/ir_normalize.py" "$W/oi.restored.ll" "$W/oi.norm0.ll" >/dev/null
python3 "$T/m5/ir5_patch.py" "$W/oi.norm0.ll" "$W/oi.lift.ll" --report "$W/ir5.json" >/dev/null 2>&1
cp "$W/oi.lift.ll" "$W/oi.p1.ll"   # comis は icall_rewrite の stub+sahf 経路で処理 (m6 ir6_pass P1 不要)
# 5b. (#2865 opt-in・既定 off) BLK 参照を module-local global @__icall_blk へ張り替え、runtime も ICALL_BLK_GLOBAL で同じ global を使う
if [ "${ICALL_BLK_GLOBAL:-0}" = "1" ]; then
  python3 "$HERE/ir_blk_global.py" "$W/oi.p1.ll" "$W/oi.p1.bg.ll" --map "$W/map.json" | tee "$W/blk_global.json"; mv "$W/oi.p1.bg.ll" "$W/oi.p1.ll"
  ICALL_EMCC_FLAGS="${ICALL_EMCC_FLAGS:-} -DICALL_BLK_GLOBAL"
fi
python3 "$HERE/ir_flatten.py" "$W/oi.p1.ll" "$W/oi.flat0.ll" --table "$W/oi.table.c" --cfg "$(python3 -c "import json;print(','.join('%x' % v for v in json.load(open('$W/map.json'))['cfg_thunks']))")"
# CRT エラー報告経路 3 関数を C override (rt/icall_ovr.c) に置換 (R の ott_ovr.c 移植)
python3 "$HERE/ir_override.py" "$W/oi.flat0.ll" "$W/oi.flat.ll" "${ICALL_OVR:-1801c8c00,1801c8cb8,1801a9a6c,1801a9b38}" | tee "$W/override.json"
python3 "$T/m11/m11_simd2.py" "$W/oi.flat.ll" 2> "$W/simd.log" | sed 's#"../msimd11_core.h"#"'"$T"'/m11/msimd11_core.h"#' > "$W/oi.simd0.c"
# 補完 helper: SSE2 5 種 (固定 C) + AVX/FMA3 VEX.128 (vex_gen.py が IR の署名から生成)。残る未実装 stub は silent (0 を返す) でなく fail-fast にする
python3 "$HERE/vex_gen.py" "$W/oi.flat.ll" "$W/oi.vex.c" | tee "$W/vex_gen.json"
python3 "$HERE/simd_merge.py" "$W/oi.simd0.c" "$W/oi.simd.c" "$HERE/rt/icall_simd_extra.c" "$W/oi.vex.c" --report "$W/simd_merge.json"
# 6. build
emcc "$W/oi.flat.ll" "$W/oi.simd.c" "$W/oi.vex.c" "$W/oi.table.c" "$HERE/rt/icall_rt.c" "$HERE/rt/icall_ovr.c" "$HERE/rt/icall_simd_extra.c" "$T/ott/work/lift/ott_data.c" \
  ${ICALL_EMCC_FLAGS:-} -w -O"${ICALL_OPT:-0}" -g -ffp-contract=off -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 -sERROR_ON_UNDEFINED_SYMBOLS=0 \
  -sEXPORTED_FUNCTIONS=_ott_run,_ott_xmm0,_ott_data_install,_malloc${ICALL_EXTRA_EXPORTS:-} -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) -o "$W/ott_route.cjs" 2> "$W/emcc.log" || { grep -v 'warning\|>>>\|^$' "$W/emcc.log" | head; exit 1; }
ls -la "$W/ott_route.cjs"
echo "[route] OK: $W/ott_route.cjs"
