#!/usr/bin/env bash
# M11 closure に tools/shimx をリンクする (CAB-166)。
#   bash tools/m11/shimx_link/build.sh [--trace] [--soft] [--fix]   → tools/m11/work/shimx_link/m11_sx_<variant>_<gui>[_fix].cjs
#     (既定)   plain / GUI fail-fast : IR は無改変, shimx を直接リンク。署名不一致/重複の検査用 (CAB-166 本体)
#     --trace  lifted 側の shimx/GUI 呼出を __sxt_ ラッパ経由にして計数 (IR の識別子を改名した別 IR を使う)
#     --soft   GUI/audio 未提供 API を fail-fast ではなく「0 返却+m11_stub_hit 計数」にする (M11 既存挙動と同じ)
#     --fix    fix_alloca.py で IR の縮退 alloca を拡幅 + cb_adapt.c (列挙系コールバックの VA→table 変換)。CAB-129 / T2 の計測用回避
#   tools/shimx と tools/m11 既存ファイルは読取のみ。成果物は全て tools/m11/work/shimx_link/ (gitignore 済)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$(cd "$HERE/.." && pwd)"
SX="$(cd "$M11/../shimx" && pwd)"
W="$M11/work/shimx_link"
TRACE=0; SOFT=0; FIX=0
for a in "$@"; do case "$a" in --trace) TRACE=1 ;; --soft) SOFT=1 ;; --fix) FIX=1 ;; esac; done
VARIANT=plain; [ $TRACE = 1 ] && VARIANT=trace
GUIV=failfast; [ $SOFT = 1 ] && GUIV=soft
SUF=""; [ $FIX = 1 ] && SUF="_fix"
TAG="${VARIANT}_${GUIV}${SUF}"
GEN="$W/gen${SUF}"; mkdir -p "$GEN"
set +u; source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1; set -u
export TMPDIR="$W/tmp"; mkdir -p "$W/obj" "$W/tmp"
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1"
SXF="-O1 -w -Wno-error=int-conversion -Wno-implicit-function-declaration -fno-strict-aliasing"   # shimx 自身のフラグ (scripts/build_objs.sh と同じ, ST)
IR0="$M11/work/boot_final3.ll"; IR="$IR0"
[ -f "$IR" ] || { echo "[sxlink] $IR 無し: bash tools/m11/m11_e2e.sh を先に (M11 成果物の生成)" >&2; exit 2; }
for f in "$M11/work/m11_fnstubs.c" "$M11/work/m11_simd.c" "$M11/work/m11_data.c" "$M11/work/boot_final3_sigs.h" "$M11/work/m11_image.bin"; do
  [ -f "$f" ] || { echo "[sxlink] $f 無し: M11 成果物が未生成" >&2; exit 2; }
done

cc() { # cc <src> <obj> [flags...] : 入力が新しければ再コンパイル
  local src="$1" obj="$2"; shift 2
  if [ ! -f "$obj" ] || [ "$src" -nt "$obj" ]; then echo "[sxlink] cc $(basename "$src")"; emcc -c "$src" -o "$obj" "$@"; fi
}

# 1. shimx 全ソース (ST; tools/shimx/src は無改変) --------------------------------
for f in "$SX"/src/*.c; do
  b="$(basename "$f" .c)"
  o="$W/obj/sx_$b.o"
  if [ -f "$o" ] && { [ "$SX/src/shimx_internal.h" -nt "$o" ] || [ "$SX/src/shimx.h" -nt "$o" ]; }; then rm -f "$o"; fi
  cc "$f" "$o" $SXF -I"$SX/src"
done
llvm-nm --defined-only -g "$W"/obj/sx_*.o > "$W/shimx_nm.txt"

# 2. m11 側 C (M11 のソースを無改変で再利用。tools/shim の 5 ファイルと m11_win.c は shimx に置換) ----
cc "$M11/m11_rt.c" "$W/obj/m11_rt.o" $CF -I"$M11"
cc "$M11/m11_ov.c" "$W/obj/m11_ov.o" $CF -I"$M11"
cc "$M11/work/m11_simd.c" "$W/obj/m11_simd.o" $CF -I"$M11"
cc "$M11/work/m11_fnstubs.c" "$W/obj/m11_fnstubs.o" $CF
cc "$M11/work/m11_data.c" "$W/obj/m11_data.o" $CF
cc "$HERE/sx_liftfix.c" "$W/obj/m11_sxfix.o" $CF
llvm-nm --defined-only -g "$W"/obj/m11_*.o > "$W/m11_nm.txt"

if [ $FIX = 1 ]; then cc "$HERE/cb_adapt.c" "$W/obj/cb_adapt.o" $CF; fi
# 2b. alloca 拡幅 (--fix) ----------------------------------------------------------
if [ $FIX = 1 ]; then
  IR="$W/boot_fixed.ll"
  if [ ! -f "$IR" ] || [ "$IR0" -nt "$IR" ] || [ "$HERE/fix_alloca.py" -nt "$IR" ]; then python3 "$HERE/fix_alloca.py" "$IR0" "$IR" --report "$W/fix_report.json"; fi
fi

# 3. 分類 + スタブ + トレースラッパ生成 ------------------------------------------
if [ ! -f "$GEN/classes.json" ] || [ "$IR" -nt "$GEN/classes.json" ] || [ "$HERE/gen_link.py" -nt "$GEN/classes.json" ] || [ "$W/shimx_nm.txt" -nt "$GEN/classes.json" ]; then
  python3 "$HERE/gen_link.py" --ir "$IR" --shimx-nm "$W/shimx_nm.txt" --m11-nm "$W/m11_nm.txt" --out "$GEN" | tee "$GEN/gen_link.log"
fi
cc "$GEN/gui_stubs_$GUIV.c" "$W/obj/gui_$GUIV$SUF.o" $CF
GUIOBJ="$W/obj/gui_$GUIV$SUF.o"
WRAP=""; if [ $FIX = 1 ]; then GUIOBJ="$GUIOBJ $W/obj/cb_adapt.o"; WRAP="-Wl,--wrap=EnumCalendarInfoW -Wl,--wrap=EnumSystemLocalesW"; fi
if [ $SOFT = 1 ]; then cc "$HERE/gui_compat.c" "$W/obj/gui_compat.o" $CF; GUIOBJ="$GUIOBJ $W/obj/gui_compat.o"; fi

# 4. IR → obj (plain: 無改変 / trace: 識別子改名済み) -----------------------------
if [ $TRACE = 1 ]; then
  cc "$GEN/boot_trace.ll" "$W/obj/boot_trace$SUF.o" $CF
  cc "$GEN/trace_wrap.c" "$W/obj/trace_wrap$SUF.o" $CF
  cc "$HERE/trace_rt.c" "$W/obj/trace_rt.o" $CF
  BOOT="$W/obj/boot_trace$SUF.o $W/obj/trace_wrap$SUF.o $W/obj/trace_rt.o"
else
  cc "$IR" "$W/obj/boot_plain$SUF.o" $CF
  BOOT="$W/obj/boot_plain$SUF.o"
fi

# 5. リンク (重複定義は error のまま = SHIM_BIND 廃止後の衝突検出) ------------------
OBJS="$W/obj/sx_*.o $W/obj/m11_rt.o $W/obj/m11_ov.o $W/obj/m11_simd.o $W/obj/m11_fnstubs.o $W/obj/m11_data.o $W/obj/m11_sxfix.o $GUIOBJ $BOOT"
EXPORTS=_m11_boot_enter,_entry_point,_m11_init_count,_m11_boot_stage,_m11_va_used,_m11_va_calls,_m11_set_trace,_m11_icall_ok,_m11_icall_miss,_m11_icall_miss_uniq,_m11_icall_miss_at,_m11_disp_count,_m11_units_run,_m11_units_total,_m11_units_skipped,_m11_stub_total,_m11_stub_uniq,_m11_stub_name,_m11_stub_count,_m11_probe_count,_m11_longjmp_hit,_m11_set_survey,_m11_call_unit,_m11_unit_va,_shimx_set_trace,_shimx_init,__emscripten_stack_restore,_emscripten_stack_get_current
OUT="$W/m11_sx_$TAG"
emcc $OBJS -o "$OUT.cjs.tmp" \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE="$((0x10000000))" \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=m11create \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 \
  --no-entry -Wl,--export-all \
  -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPF32,HEAP32,HEAPF64,HEAPU32,HEAP64,wasmTable,addFunction,ENV \
  -sEXPORTED_FUNCTIONS=$EXPORTS \
  -Wl,--initial-memory="$((0x13000000))" -Wl,--max-memory="$((0x72000000))" $WRAP 2> "$W/link_$TAG.log" || { tail -30 "$W/link_$TAG.log"; echo "[sxlink] リンク失敗 ($TAG)"; exit 1; }
mv "$OUT.cjs.tmp" "$OUT.cjs"
python3 "$M11/m11_postjs.py" "$OUT.cjs" 2>/dev/null || true
echo "[sxlink] OK $TAG: signature mismatch=$(grep -c 'signature mismatch' "$W/link_$TAG.log" || true) undefined symbol=$(grep -c 'undefined symbol' "$W/link_$TAG.log" || true) duplicate=$(grep -c 'duplicate symbol' "$W/link_$TAG.log" || true)  -> $OUT.cjs"
