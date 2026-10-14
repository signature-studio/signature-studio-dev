#!/usr/bin/env bash
# M11 closure に tools/shimx をリンクする (CAB-166)。
#   bash tools/m11/shimx_link/build.sh [--trace] [--soft] [--fix] [--ws]   → tools/m11/work/shimx_link/m11_sx_<variant>_<gui>[_fix][_ws].cjs
#     (既定)   plain / GUI fail-fast : IR は無改変, shimx を直接リンク。署名不一致/重複の検査用 (CAB-166 本体)
#     --trace  lifted 側の shimx/GUI 呼出を __sxt_ ラッパ経由にして計数 (IR の識別子を改名した別 IR を使う)
#     --soft   GUI/audio 未提供 API を fail-fast ではなく「0 返却+m11_stub_hit 計数」にする (M11 既存挙動と同じ)
#     --fix    fix_alloca.py で IR の縮退 alloca を拡幅 + sx_liftfix.c (_WStrClr)。CAB-129 計測用回避
#              (旧 cb_adapt.c の列挙コールバック変換は CAB-177 で shimx R2 実体 (cbtrans) + sx_cbboot に置換済み。
#               R2/R3 接続は --fix 無しの全 variant で constructor 実行: -Wl,--wrap=m11_icall 含む)
#     --ws   tools/startup/winstubs を結線 (#223): winstubs 全ソース + wrap_list.txt の -Wl,--wrap=<api> (12 本)、
#            sx_winstubs.c (constructor で winstubs_init(0))、__asm_cpuid の実体を winstubs_cpuid 委譲に置換 (m11_simd2.py --cpuid=winstubs)。
#            winstubs が定義する API (weak 含む) は gui/audio スタブを生成しない (gen_link の m11 nm に ws_*.o を加える)
#   tools/shimx と tools/m11 既存ファイルは読取のみ。成果物は全て tools/m11/work/shimx_link/ (gitignore 済)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$(cd "$HERE/.." && pwd)"
SX="$(cd "$M11/../shimx" && pwd)"
W="$M11/work/shimx_link"
TRACE=0; SOFT=0; FIX=0; WS=0; MIDI=0
for a in "$@"; do case "$a" in --trace) TRACE=1 ;; --soft) SOFT=1 ;; --fix) FIX=1 ;; --ws) WS=1 ;; --midi) MIDI=1 ;; esac; done
VARIANT=plain; [ $TRACE = 1 ] && VARIANT=trace
GUIV=failfast; [ $SOFT = 1 ] && GUIV=soft
SUF=""; [ $FIX = 1 ] && SUF="_fix"
WSUF=""; [ $WS = 1 ] && WSUF="_ws"
MSUF=""; [ $MIDI = 1 ] && MSUF="_midi"
TAG="${VARIANT}_${GUIV}${SUF}${WSUF}${MSUF}"
GEN="$W/gen${SUF}${WSUF}"; mkdir -p "$GEN"
WSD="$(cd "$M11/../startup/winstubs" && pwd)"
set +u; source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1; set -u
export PATH="/opt/emsdk/upstream/bin:$PATH"   # emsdk_env.sh は upstream/bin を PATH から外すため llvm-nm が見つからない (#773)
export TMPDIR="$W/tmp"; mkdir -p "$W/obj" "$W/tmp"
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0}"
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
cc "$HERE/sx_cbboot.c" "$W/obj/sx_cbboot.o" $CF   # CAB-177: R2 translator 実体 + R3 トークン (全 variant, constructor)
llvm-nm --defined-only -g "$W"/obj/m11_*.o > "$W/m11_nm.txt"

# 2c. winmm midi* 強定義 (--midi, #179 SHX-T6) ----------------------------------------
#   audio 側の flm_midi* (flmidi*.c) を同リンクへ入れ、sx_midi_boot.c の constructor で
#   flmidi_shimx_install() を呼んで shimx の midi* backend 表を登録する。--midi 無しの variant は不変。
MIDIOBJ=""
if [ $MIDI = 1 ]; then
  AUD="$(cd "$M11/../audio/src" && pwd)"
  mkdir -p "$W/obj_midi"
  # flmidi.c は wasm atomics (shared memory) 前提。closure の本体は非 atomics のまま、MIDI objs だけ atomics を付ける
  MIDIF="-O1 -w -matomics -mbulk-memory -pthread -fno-strict-aliasing"
  for b in flmidi flmidi_winmm flmidi_shimx; do cc "$AUD/$b.c" "$W/obj_midi/$b.o" $MIDIF -I"$AUD" -I"$SX/src"; done
  cc "$HERE/sx_midi_boot.c" "$W/obj_midi/sx_midi_boot.o" $MIDIF -I"$AUD"
  MIDIOBJ="$W/obj_midi/flmidi.o $W/obj_midi/flmidi_winmm.o $W/obj_midi/flmidi_shimx.o $W/obj_midi/sx_midi_boot.o"
fi

# 2a. winstubs 結線 (--ws, #223) -------------------------------------------------------
#   winstubs 全ソース (tools/startup/winstubs/src は読取のみ) + link 側 glue + cpuid 委譲版 simd helper。
#   m11_simd_ws.c は work/ (m11_simd.c と同階層) に置く: 生成物の "../msimd11_core.h" がそのまま解決される。
WSLINK=""
if [ $WS = 1 ]; then
  mkdir -p "$W/obj_ws"
  for f in "$WSD"/src/*.c; do b="$(basename "$f" .c)"; cc "$f" "$W/obj_ws/$b.o" $SXF -I"$SX/src" -I"$WSD/src"; done
  cc "$HERE/sx_winstubs.c" "$W/obj_ws/sx_winstubs.o" $CF -I"$SX/src" -I"$WSD/src"
  SIMD_WS="$M11/work/m11_simd_ws.c"
  if [ ! -f "$SIMD_WS" ] || [ "$M11/work/boot_final.ll" -nt "$SIMD_WS" ] || [ "$M11/m11_simd2.py" -nt "$SIMD_WS" ]; then
    python3 "$M11/m11_simd2.py" "$M11/work/boot_final.ll" --cpuid=winstubs > "$SIMD_WS" 2> "$M11/work/simd2_ws.log"
  fi
  cc "$SIMD_WS" "$W/obj_ws/m11_simd_ws.o" $CF -I"$M11"
  llvm-nm --defined-only -g "$W"/obj_ws/*.o > "$W/ws_nm.txt"
  cat "$W/m11_nm.txt" "$W/ws_nm.txt" > "$W/m11ws_nm.txt"
  while read -r s; do [ -z "$s" ] || WSLINK="$WSLINK -Wl,--wrap=$s"; done < <(grep -v '^#' "$WSD/wrap_list.txt")
fi

# 2b. alloca 拡幅 (--fix) ----------------------------------------------------------
#   (旧 --fix 構成要素の cb_adapt.c は sx_cbboot.c + shimx cbtrans に置換済み = CAB-177 正式化)
if [ $FIX = 1 ]; then
  IR="$W/boot_fixed.ll"
  if [ ! -f "$IR" ] || [ "$IR0" -nt "$IR" ] || [ "$HERE/fix_alloca.py" -nt "$IR" ]; then python3 "$HERE/fix_alloca.py" "$IR0" "$IR" --report "$W/fix_report.json"; fi
fi

# 3. 分類 + スタブ + トレースラッパ生成 ------------------------------------------
M11NM="$W/m11_nm.txt"; [ $WS = 1 ] && M11NM="$W/m11ws_nm.txt"
if [ ! -f "$GEN/classes.json" ] || [ "$IR" -nt "$GEN/classes.json" ] || [ "$HERE/gen_link.py" -nt "$GEN/classes.json" ] || [ "$W/shimx_nm.txt" -nt "$GEN/classes.json" ] || [ "$M11NM" -nt "$GEN/classes.json" ]; then
  python3 "$HERE/gen_link.py" --ir "$IR" --shimx-nm "$W/shimx_nm.txt" --m11-nm "$M11NM" --out "$GEN" | tee "$GEN/gen_link.log"
fi
cc "$GEN/gui_stubs_$GUIV.c" "$W/obj/gui_$GUIV$SUF$WSUF.o" $CF
GUIOBJ="$W/obj/gui_$GUIV$SUF$WSUF.o"
# CAB-177: --wrap=m11_icall (R3 トークン → lifttab thunk → 実体。それ以外は __real_m11_icall)
WRAP="-Wl,--wrap=m11_icall"
if [ $SOFT = 1 ]; then cc "$HERE/gui_compat.c" "$W/obj/gui_compat.o" $CF; GUIOBJ="$GUIOBJ $W/obj/gui_compat.o"; fi

# 4. IR → obj (plain: 無改変 / trace: 識別子改名済み) -----------------------------
if [ $TRACE = 1 ]; then
  cc "$GEN/boot_trace.ll" "$W/obj/boot_trace$SUF$WSUF.o" $CF
  cc "$GEN/trace_wrap.c" "$W/obj/trace_wrap$SUF$WSUF.o" $CF
  cc "$HERE/trace_rt.c" "$W/obj/trace_rt.o" $CF
  BOOT="$W/obj/boot_trace$SUF$WSUF.o $W/obj/trace_wrap$SUF$WSUF.o $W/obj/trace_rt.o"
else
  cc "$IR" "$W/obj/boot_plain$SUF.o" $CF
  BOOT="$W/obj/boot_plain$SUF.o"
fi

# 5. リンク (重複定義は error のまま = SHIM_BIND 廃止後の衝突検出)
#    ※ $W/obj/sx_*.o glob は shimx 各 .o に加え sx_cbboot.o も拾う (CAB-177)
#    --ws 時は m11_simd.o を外し (cpuid 委譲版 m11_simd_ws.o で置換)、obj_ws/*.o を足す。
#    配列 + "$W" 引用で組む: $W に glob 文字/空白が入っても展開されるのは sx_*.o / obj_ws/*.o の意図した glob だけ。
OBJS=("$W"/obj/sx_*.o "$W/obj/m11_rt.o" "$W/obj/m11_ov.o")
[ $WS = 1 ] || OBJS+=("$W/obj/m11_simd.o")
OBJS+=("$W/obj/m11_fnstubs.o" "$W/obj/m11_data.o" "$W/obj/m11_sxfix.o")
read -ra _multi <<< "$GUIOBJ $BOOT"   # GUIOBJ/BOOT は複数 .o の空白区切り。read -a は分割のみで glob 展開しない
OBJS+=("${_multi[@]}")
[ $WS = 1 ] && OBJS+=("$W"/obj_ws/*.o)
[ $MIDI = 1 ] && read -ra _midi <<< "$MIDIOBJ" && OBJS+=("${_midi[@]}")
WSEXP=""; [ $WS = 1 ] && WSEXP=_sx_ws_probe_cpuid,_sx_ws_probe_g03,_sx_ws_probe_g12,_sx_ws_stat,_sx_ws_loadlib_miss,_winstubs_stats,_winstubs_loadlib_miss,_winstubs_cpuid,
[ $MIDI = 1 ] && WSEXP="${WSEXP}_sx_midi_probe_numdevs,_flm_init,"
EXPORTS=_m11_boot_enter,_entry_point,_m11_init_count,_m11_boot_stage,_m11_va_used,_m11_va_calls,_m11_set_trace,_GetLastError,_m11_icall_ok,_m11_icall_miss,_m11_icall_miss_uniq,_m11_icall_miss_at,_m11_disp_count,_m11_units_run,_m11_units_total,_m11_units_skipped,_m11_stub_total,_m11_stub_uniq,_m11_stub_name,_m11_stub_count,_m11_probe_count,_m11_longjmp_hit,_m11_set_survey,_m11_call_unit,_m11_unit_va,_sxt_n,_sxt_name,_sxt_count,_sxt_ret_n,_sxt_ret_unit,_sxt_ret_idx,_sxt_ret_site,_sxt_site_name,_sxt_ret_a,_sxt_ret_b,_sxt_ret_r,_shimx_set_trace,_shimx_set_trace_file,_shimx_init,${WSEXP}__emscripten_stack_restore,_emscripten_stack_get_current
OUT="$W/m11_sx_$TAG"
emcc "${OBJS[@]}" -o "$OUT.cjs.tmp" \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE="$((0x10000000))" \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=m11create \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 \
  --no-entry -Wl,--export-all \
  -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPF32,HEAP32,HEAPF64,HEAPU32,HEAP64,wasmTable,addFunction,ENV,ccall,FS \
  -sEXPORTED_FUNCTIONS=$EXPORTS \
  -Wl,--initial-memory="$((0x13000000))" -Wl,--max-memory="$((0x72000000))" $WRAP $WSLINK 2> "$W/link_$TAG.log" || { tail -30 "$W/link_$TAG.log"; echo "[sxlink] リンク失敗 ($TAG)"; exit 1; }
mv "$OUT.cjs.tmp" "$OUT.cjs"
python3 "$M11/m11_postjs.py" "$OUT.cjs" 2>/dev/null || true
echo "[sxlink] OK $TAG: signature mismatch=$(grep -c 'signature mismatch' "$W/link_$TAG.log" || true) undefined symbol=$(grep -c 'undefined symbol' "$W/link_$TAG.log" || true) duplicate=$(grep -c 'duplicate symbol' "$W/link_$TAG.log" || true)  -> $OUT.cjs"
