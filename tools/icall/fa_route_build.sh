#!/usr/bin/env bash
# fa_route_build.sh — Fresh Air SlateCore closure の wasm route (ICALL-28 #1451)。
#   入力: work/rt_freshair-core/after.0.restored.ll (rewrite + RetDec decode-only 済み。素材 work-icall)
#         + work/rt_freshair-core/map.json (blk / stub) + SlateCore.core_64 (素材 plugins-freshair)
#   出力: work/fa_route/fa_route.{cjs,wasm}
#   範囲: 復元後 IR → fix_mask/fix_vstore → normalize/ir5 → flatten → SIMD/VEX helper → data 敷設 → emcc。
#   ott_route.sh との差: (1) flatten の --limit を画像全域 (0x10000000) へ広げる (SlateCore の BLK 0x186319000 は既定 limit 外)
#                        (2) emcc に -DICALL_BLK=0x36319000 と 0x3c000000 のメモリを渡す (BLK は map.json の blk を shift した値)
#                        (3) data_gen.py で .rdata/.data/_RDATA を敷設 (ott_data_install を空にしない)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
T="$HERE/.."
W="$HERE/work/fa_route"; mkdir -p "$W/tmp"
SRC="${FA_SRC:-$HERE/work/rt_freshair-core/after.0.restored.ll}"
MAP="${FA_MAP:-$HERE/work/rt_freshair-core/map.json}"
DLL="${FA_CORE:-$T/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64}"
if [ ! -f "$SRC" ] || [ ! -f "$MAP" ]; then echo "[fa_route] $SRC / $MAP が無い: 素材 work-icall を展開 (tools/icall/work/rt_freshair-core)" >&2; exit 2; fi
# ICALL-97 (#4290): roundtrip.sh の CHUNKS=N が出した全 chunk を統合する (chunk 0 だけでは入口表に入らない関数が出る)
if [ -z "${FA_SRC:-}" ] && ls "$(dirname "$SRC")"/after.[1-9]*.restored.ll >/dev/null 2>&1; then
  python3 "$HERE/ir_merge_restored.py" "$W/merged.restored.ll" "$(dirname "$SRC")"/after.[0-9]*.restored.ll; SRC="$W/merged.restored.ll"
fi
if [ ! -f "$DLL" ]; then echo "[fa_route] $DLL が無い: 素材 plugins-freshair を展開し tools/targets/freshair/fetch.sh を実行" >&2; exit 2; fi
BLK_SHIFTED="$(python3 -c "import json,sys;m=json.load(open(sys.argv[1]));print(hex(m['blk']-0x180000000+0x30000000))" "$MAP")"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
# 1. 復元後 IR の後処理
# ICALL-70: cookie global (0x18125eaa8) の load 幅 i32 → i64 (RetDec の global 型決定段が i32 と型付け、#2262 付録 §3)
# 既定 ON (#2302): 初期値 COOKIE_INIT は SlateCore.core_64 の .data 実値 (VA 0x18125eaa8 = 0x2b992ddfa232) と一致する。FA_FIX_COOKIE=0 で従来の i32 に戻す (REPORT_APPENDIX_2302 §2)
if [ "${FA_FIX_COOKIE:-1}" = "1" ]; then
  python3 "$HERE/ir_fix_cookie.py" "$SRC" "$W/cookie_fixed.ll" > "$W/fix_cookie.json"; SRC_FIX="$W/cookie_fixed.ll"
else
  SRC_FIX="$SRC"
fi
# ICALL-77 (#2427): 機械語の脱落 frame slot store を IR に戻し、隣接 slot を 1 alloca にまとめる (frame_slot_restore.py)。既定 OFF。FA_FRAME_SLOT=1 で有効化
if [ "${FA_FRAME_SLOT:-0}" = "1" ]; then
  RTD="$HERE/work/rt_freshair-core"
  python3 "$HERE/frame_slot_restore.py" --ir "$SRC_FIX" --dsm "$RTD/before.0.drc.dsm" --before-ll "$RTD/before.0.drc.ll" --ranges "$RTD/F.ranges" --out "$W/frame_slot.ll" --report "$W/frame_slot.json"
  SRC_FIX="$W/frame_slot.ll"
fi
python3 "$HERE/ir_fix_mask.py" "$SRC_FIX" "$W/oi.restored.ll" > "$W/fix_mask.json"
python3 "$HERE/ir_fix_vstore.py" "$W/oi.restored.ll" "$W/oi.restored1.ll" > "$W/fix_vstore.json"; mv "$W/oi.restored1.ll" "$W/oi.restored.ll"
# 2. normalize / ir5_patch → flatten (画像全域を shift)
python3 "$T/m2/ir_normalize.py" "$W/oi.restored.ll" "$W/oi.norm0.ll" >/dev/null
python3 "$T/m5/ir5_patch.py" "$W/oi.norm0.ll" "$W/oi.lift.ll" --report "$W/ir5.json" >/dev/null 2>&1
cp "$W/oi.lift.ll" "$W/oi.p1.ll"
python3 "$HERE/ir_flatten.py" "$W/oi.p1.ll" "$W/oi.flat0.ll" --table "$W/oi.table.c" --limit 0x10000000
# override 対象は closure 外なら missing になる (exit 1)。出力 IR は書かれるので無視する
python3 "$HERE/ir_override.py" "$W/oi.flat0.ll" "$W/oi.flat.ll" "${ICALL_OVR:-1801c8c00,1801c8cb8,1801a9a6c,1801a9b38}" | tee "$W/override.json" || true
# 3. SIMD / VEX helper
M11="$(cd -- "$T/m11" && pwd)"
python3 "$T/m11/m11_simd2.py" "$W/oi.flat.ll" 2> "$W/simd.log" > "$W/oi.simd0.c"
sed -i "s#\"../msimd11_core.h\"#\"$M11/msimd11_core.h\"#; s#\"../m11/msimd11_core.h\"#\"$M11/msimd11_core.h\"#" "$W/oi.simd0.c"
python3 "$HERE/vex_gen.py" "$W/oi.flat.ll" "$W/oi.vex.c" > "$W/vex_gen.json"
python3 "$HERE/simd_merge.py" "$W/oi.simd0.c" "$W/oi.simd.c" "$HERE/rt/icall_simd_extra.c" "$W/oi.vex.c" --report "$W/simd_merge.json" >/dev/null
# 4. data 敷設 (.rdata/.data/_RDATA, DIR64 補正済み)
python3 "$T/ott/lift/data_gen.py" "$DLL" "$W/fa_data.c" > /dev/null
# ICALL-55: native の FA_ENC_INIT=1 と同じ encoded slot 初期化 (enc(NULL)=cookie) を data install の末尾に足す
if [ "${FA_ENC_INIT:-0}" = "1" ]; then
python3 - "$W/fa_data.c" <<'PY'
import sys
COOKIE = 0x18125eaa8 - 0x180000000 + 0x30000000
SLOTS = [0x1813068d0, 0x1813068f8, 0x181306900, 0x181306908, 0x181306910, 0x1813072b0,
         0x1813073f0, 0x1813073f8, 0x181307400, 0x181307408, 0x181307410, 0x181307418]
p = sys.argv[1]
src = open(p).read().rstrip()
assert src.endswith('}')
add = ''.join('  *(uint64_t*)0x%xu = *(uint64_t*)0x%xu;\n' % (s - 0x180000000 + 0x30000000, COOKIE) for s in SLOTS)
open(p, 'w').write(src[:-1] + add + '}\n')
PY
fi
# 5. build (BLK = $BLK_SHIFTED, memory 0x3c000000)
emcc "$W/oi.flat.ll" "$W/oi.simd.c" "$W/oi.vex.c" "$W/oi.table.c" "$W/fa_data.c" "$HERE/rt/icall_rt.c" "$HERE/rt/icall_ovr.c" "$HERE/rt/icall_simd_extra.c" \
  -DICALL_BLK=$BLK_SHIFTED -w -O0 -g -ffp-contract=off -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 -sERROR_ON_UNDEFINED_SYMBOLS=0 \
  -sEXPORTED_FUNCTIONS=_ott_run,_ott_xmm0,_ott_data_install,_malloc -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x3c000000)) -Wl,--max-memory=$((0x3c000000)) -o "$W/fa_route.cjs" 2> "$W/emcc.log" || { grep -v 'warning' "$W/emcc.log" | head; exit 1; }
ls -la "$W/fa_route.cjs" "$W/fa_route.wasm"
echo "[fa_route] OK: $W/fa_route.cjs"
