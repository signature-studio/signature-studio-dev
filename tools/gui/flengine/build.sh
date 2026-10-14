#!/usr/bin/env bash
# GUI-3 (#174): m11 の FLEngine lift (work/boot_final3.ll) に tools/gui shim を結合した wasm を作る。
#   bash tools/gui/flengine/build.sh [--plain] [--soft] [--base]   → $GF_W/m11_gui[_soft|_plain].cjs(+wasm) / --base は $GF_W/m11_base.cjs
#     --plain: --reach 無し = 到達ログ無しの通常ビルド / --soft: 未実装 (STUB) API を fail-fast 例外ではなく 0 返却+SOFT-STUB 行にする
#       (1 unit 目の未実装 API で脱出せず、後続の API まで含めた到達集合を取る計測用。shim の実装ではない)
# 前提: GF_M11 (e2e.sh では複製先 $GF_W/tree/m11) で m11_build.sh が一度通っていること (boot_final3.ll / *_sigs.h / simd / fnstubs / data / image が $GF_M11/work に出る)。
# GF_M11 は読取のみ。m11_build.sh の除外リスト方式 (M11_EXCLUDE) で GUI 名を winstubs から外し shim 定義へ切替える。
# 全 TU を -pthread で揃える (INTEGRATION.md §4-3)。成果物は tools/gui/work/flengine/ (gitignore 済)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; source "$HERE/env.sh"
REACH="--reach"; SOFT=0; TAG=""; BASE=0
for a in "$@"; do case "$a" in --plain) REACH=""; TAG="_plain" ;; --soft) SOFT=1; TAG="_soft" ;; --base) BASE=1; TAG="_base" ;; esac; done
[ $BASE = 1 ] && OUT="m11_base" || OUT="m11_gui$TAG"
W="$GF_W"; M="$GF_M11"; MW="$M/work"; mkdir -p "$W/obj" "$W/gen" "$W/tmp"
export TMPDIR="$W/tmp"
for f in boot_final.ll boot_final3.ll boot_final3_sigs.h m11_simd.c m11_fnstubs.c m11_data.c m11_image.bin; do
  [ -f "$MW/$f" ] || { echo "[gf] $MW/$f 無し: bash tools/m11/m11_build.sh を先に" >&2; exit 2; }
done
M11_LB_BASE="${M11_LB_BASE:-0}"
M11_OV_CLASSCREATE="${M11_OV_CLASSCREATE:-0}"   # m11_build.sh と同じ -D を揃える (m11_ov.c の既定も 0)
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -pthread -DM11_LB_BASE=$M11_LB_BASE -DM11_OV_CLASSCREATE=$M11_OV_CLASSCREATE"
cc() { local src="$1" obj="$2"; shift 2
  if [ ! -f "$obj" ] || [ "$src" -nt "$obj" ]; then echo "[gf] cc $(basename "$src")"; emcc -c "$src" -o "$obj" "$@"; fi; }

# 1. GUI shim (-pthread, IR の GUI declare 署名 adapter 付き)。--base は shim 無し (比較元) なので作らない
rm -rf "$W/gui"; mkdir -p "$W/gui"
if [ $BASE = 0 ]; then bash "$GF_GUI/integ/build_objs.sh" "$W/gui" $REACH --ir "$MW/boot_final.ll"; fi
if [ $SOFT = 1 ]; then   # gui_stubs.c の `gui_failfast("X", 0);` を `return gf_soft_stub("X");` にした版で差し替える
  sed -e '/^extern void gui_failfast/d' -e 's/gui_failfast(\("[A-Za-z0-9_]*"\), 0);/return gf_soft_stub(\1);/' -e '2a extern int64_t gf_soft_stub(const char *api);' "$GF_GUI/build/gui_stubs.c" > "$W/gen/gui_stubs_soft.c"
  emcc -c -O1 -fwrapv -w -fno-strict-aliasing -pthread -I "$GF_GUI/include" -I "$GF_GUI/src" -I "$GF_GUI/build" -DGUI_NO_K32 -include "$GF_GUI/build/gui_rename.h" "$W/gen/gui_stubs_soft.c" -o "$W/gui/gui_stubs.o"
  llvm-nm --defined-only "$W"/gui/*.o | awk '$2 ~ /^[TtWwDdBbRr]$/ {print $3}' | sort -u > "$W/gui/exports.txt"
fi

# 2. m11 側 C を -pthread で再コンパイル (m11_win.c の user32 3 本は shim 定義と衝突するため改名してリンクから実質除外)
for f in heap failfast file timer sync; do cc "$M/../shim/src/$f.c" "$W/obj/shim_$f.o" $CF; done
cc "$M/m11_rt.c" "$W/obj/rt.o" $CF -I"$M"
cc "$M/m11_win.c" "$W/obj/win.o" $CF -I"$M" -DLoadStringW=m11_win_LoadStringW -DMessageBoxA=m11_win_MessageBoxA -DMessageBoxW=m11_win_MessageBoxW -DEnumDisplayMonitors=m11_win_EnumDisplayMonitors -DGetMonitorInfoW=m11_win_GetMonitorInfoW
cc "$M/m11_ov.c" "$W/obj/ov.o" $CF -I"$M" -I"$MW"
cc "$MW/m11_simd.c" "$W/obj/simd.o" $CF -I"$M"
cc "$MW/m11_fnstubs.c" "$W/obj/fnstubs.o" $CF
cc "$MW/m11_data.c" "$W/obj/data.o" $CF
PE="${FL_WIN64_DIR:-}/extracted/block00031_PE.bin"
if [ -f "$PE" ] && python3 -c 'import pefile' 2>/dev/null; then python3 "$HERE/gen_thunks.py" "$PE" "$W/gen/gf_thunks.c" "$M11_LB_BASE"
else echo "[gf] WARNING: PE または pefile 無し: import thunk 表が空 (DefWindowProc thunk を WNDPROC に持つ窓は作れない)" >&2
  echo 'const unsigned long long gf_thunk_va[] = {0}; const int gf_thunk_kind[] = {0}; const int gf_thunk_n = 0;' > "$W/gen/gf_thunks.c"; fi
if [ $BASE = 0 ]; then
cc "$W/gen/gf_thunks.c" "$W/obj/gf_thunks.o" $CF
cc "$HERE/flengine_glue.c" "$W/obj/glue.o" $CF -I"$GF_GUI/src" -I"$GF_GUI/include"
fi

# 3. winstubs: C 側定義 + GUI shim 定義を除外リストにして生成 (m11_build.sh と同方式)
llvm-nm --defined-only "$W"/obj/shim_*.o "$W/obj/rt.o" "$W/obj/win.o" 2>/dev/null | awk '$2 ~ /^[TtWwDd]$/ {print $3}' > "$W/gen/c_defined.txt"
if [ $BASE = 1 ]; then : > "$W/gui/exports.txt"; fi
cat "$W/gen/c_defined.txt" "$W/gui/exports.txt" | sort -u > "$W/gen/exclude.txt"
M11_EXCLUDE="$W/gen/exclude.txt" python3 "$M/m11_genstubs.py" "$MW/boot_final.ll" "$W/gen" > "$W/gen/genstubs.log"
cc "$W/gen/m11_winstubs.c" "$W/obj/winstubs.o" $CF
cc "$MW/boot_final3.ll" "$W/obj/boot.o" $CF

# 4. 重複定義の事前検査 (wasm-ld duplicate symbol の前に名前を出す)
llvm-nm --defined-only -g "$W"/obj/*.o "$W"/gui/*.o 2>/dev/null | awk '$2 ~ /^[TDBRWV]$/ {print $3}' | sort | uniq -d > "$W/gen/dups.txt" || true
echo "[gf] strong 重複定義シンボル: $(grep -c . "$W/gen/dups.txt" || true)"

# 5. リンク
EXPORTS=$(sed -n 's/^EXPORTS=//p' "$M/m11_build.sh" | head -1),_malloc,_free
if [ $BASE = 0 ]; then EXPORTS="$EXPORTS,_gui_shared_ptr,_gui_shared_size,_gui_reach_dump,_gui_reach_json,_gui_reach_distinct,_gui_reach_calls,_gf_icall_count,_gf_thunk_count,_gf_ring_discarded,_gf_failfast_count,_gf_soft_stub_count,_CreateFruityInstance"; fi
GUI_OBJS=$(ls "$W"/gui/*.o 2>/dev/null || true)
if [ $BASE = 1 ]; then rm -f "$W/obj/glue.o" "$W/obj/gf_thunks.o"; fi   # 前回の GUI 結合 build の残骸を比較元に混ぜない
emcc "$W"/obj/*.o $GUI_OBJS -o "$W/$OUT.cjs.tmp" \
  -O0 -g1 -pthread -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE="$((0x10000000))" \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=m11create \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sPTHREAD_POOL_SIZE=0 \
  --no-entry -Wl,--export-all \
  -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPF32,HEAP32,HEAPF64,HEAPU32,HEAP64,wasmTable,addFunction,wasmMemory \
  -sEXPORTED_FUNCTIONS=$EXPORTS $( [ $BASE = 1 ] || echo -Wl,--wrap=gui_failfast ) \
  -sINITIAL_MEMORY="$((0x12000000))" -sMAXIMUM_MEMORY="$((0x72000000))" 2> "$W/link.log" || { tail -30 "$W/link.log"; exit 1; }
mv "$W/$OUT.cjs.tmp" "$W/$OUT.cjs"
python3 "$M/m11_postjs.py" "$W/$OUT.cjs" 2>/dev/null || true
echo "[gf] OK: $W/$OUT.cjs  signature mismatch: $(grep -c 'signature mismatch' "$W/link.log" || true), undefined symbol: $(grep -c 'undefined symbol' "$W/link.log" || true), duplicate symbol: $(grep -c 'duplicate symbol' "$W/link.log" || true)"
