#!/usr/bin/env bash
# qfc_trace_4263.sh — 経路 B (longjmp 0x40f9c0) の実行時トレース (T-SH-107 / #4263)。測定専用・判定はしない。
#   前提: qfc_boot.sh を 1 回実行して work/boot/lift が存在すること (lift・soft stub の入力に使う)。FL_WIN64_DIR 必須。
#   出力: work/trace4263/trace.log (DllMain → GetStats の段ごとの [trace4263] 行)。
#   測定内容: f_40f430 / f_40fb80 / f_40fa40 の入口で flag [0x5d0cb0]・record [0x5d0c80] を出し、
#             qfc_ov_longjmp の入口で flag・caller 戻り番地・スタック上の lift 戻り番地を出す。
#   lift の関数本体はコピーに対して差し込み (work/ 内のみ)。tools 側の lift・override は変更しない。
set -euo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/env.sh"
cd "$QFC"
L="$QFC/work/boot/lift"; T="$QFC/work/trace4263"
[ -f "$L/lift_meta.json" ] || { echo "[qfc_trace_4263] lift が無い: 先に qfc_boot.sh を実行"; exit 2; }
mkdir -p "$T/lift2"
"$QFC_PY" - "$L/fle_lifted.c" "$T/lift2/fle_lifted.c" <<'PY'
import sys
src = open(sys.argv[1]).read()
dbg = ' { fprintf(stderr,"[trace4263] ENTER %s flagB=%u recB=%#llx\\n",(unsigned)LD8(0x5d0cb0),(unsigned long long)LD64(0x5d0c80)); }\n'
for fn in ('f_40f430', 'f_40fb80', 'f_40fa40'):
    i = src.index(f'void {fn}(void) {{\nL_')
    j = src.index('\n', src.index(';', i)) + 1
    src = src[:j] + dbg.replace('ENTER %s', f'ENTER {fn}') + src[j:]
# 経路 A (0x40fbcf) と経路 B (0x40fcb8) の呼出し直前で、発火の有無と flag を出す (CALL_A / CALL_B)。
for va, tag in (('40fbcf', 'CALL_A'), ('40fcb8', 'CALL_B')):
    tgt = f'/* {va}: call 0x40fa40 */\n'
    assert src.count(tgt) == 1, tgt
    src = src.replace(tgt, tgt + f' {{ fprintf(stderr,"[trace4263] {tag} flagA=%u flagB=%u\\n",(unsigned)LD8(0x5d0db0),(unsigned)LD8(0x5d0cb0)); }}\n')
open(sys.argv[2], 'w').write('#include <stdio.h>\n' + src)
PY
emcc -O0 -ffp-contract=off -fno-fast-math -I../flelift/rt -I../shared/oss/freetype -I"$FT_SRC_INC" "$T/lift2/fle_lifted.c" "$L/fle_data.c" "$L/soft_imp.c" qfc_imp.c "$QFC/qfc_ov_trace_4263.c" ../shared/oss/freetype/qfc_import.c "$FT_WASM32_LIB" ../flelift/rt/fle_cpu.c ../flelift/rt/fle_glue.c \
  -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -sEXIT_RUNTIME=1 -sEXPORTED_FUNCTIONS=_fle_run,_fle_xmm0,_fle_xmm1,_fle_rget,_fle_mget,_fle_set_stackarg,_fle_data_install,_fle_init,_fle_reset,_malloc,_qfc_run \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
  -o "$T/qfcl_trace.cjs"
QFC_CJS="$T/qfcl_trace.cjs" timeout 300 node "$QFC/qfc_trace_4263.mjs" > "$T/trace.log" 2>&1 || true
grep -E '\[trace4263\]|\[ret\]|\[trap\]' "$T/trace.log"
echo "[qfc_trace_4263] ENTER=$(grep -c 'ENTER' "$T/trace.log") CALL_A=$(grep -c 'CALL_A' "$T/trace.log") CALL_B=$(grep -c 'CALL_B' "$T/trace.log")"
