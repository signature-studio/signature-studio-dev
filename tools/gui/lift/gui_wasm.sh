#!/usr/bin/env bash
# gui_wasm.sh — lifted.c + shim を emcc で wasm (pthread, SAB) 化。usage: gui_wasm.sh <lifted.c> <outdir> [fixed|grow|reach]
#   fixed: 128MB 固定 / grow: 3MB 初期 + ALLOW_MEMORY_GROWTH (worker が memory.buffer を取り直せることの検証用)
#   reach: fixed + 到達 API ログ (shim 本体を gui_impl_<Name> へ改名し、reach hit 付き wrapper 経由で公開; CAB-156)
#   GUI-13 (#615): 既定で gui_ft.c + gui_ft_wasm.c + wasm32 pthread libfreetype (lift/ft_wasm_lib.sh) を組込む。host (JS) が gui_ft_add_face を呼ぶまで text engine は未登録 = 内蔵 8x8 のまま。
#   GUI_NO_FT=1 で組込まない (従来ビルド; libfreetype 不要)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; BUILD="$ROOT/build"
LIFTED="$1"; OUT="$2"; VARIANT="${3:-fixed}"; mkdir -p "$OUT"
if [ "$VARIANT" = grow ]; then MEMFLAGS=(-sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=3145728 -sMAXIMUM_MEMORY=1073741824 -sSTACK_SIZE=524288)
else MEMFLAGS=(-sINITIAL_MEMORY=134217728 -sSTACK_SIZE=1048576); fi
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v emcc >/dev/null || { echo "emcc not found" >&2; exit 2; }
python3 "$ROOT/gen_api.py" >/dev/null
# 定型: tools/m1/flags.sh の CLANG_FLAGS 系に準拠 (lifter 産 C 向けに -w/-Wno-error=int-conversion, -fwrapv)
SIMD=(-msimd128); [ "${GUI_NO_SIMD:-0}" = 1 ] && SIMD=(-DGUI_NO_SIMD)   # GUI-5: gui_simd.h の行カーネルを wasm SIMD128 で (GUI_NO_SIMD=1 で scalar 参照ビルド)
CFLAGS=("${SIMD[@]}" -O1 -fwrapv -w -fno-strict-aliasing -pthread
  -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=int-to-pointer-cast -Wno-error=implicit-function-declaration
  -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD")
FT_OBJS=(); FT_EXPORTS=""
if [ "${GUI_NO_FT:-0}" != 1 ]; then
  FTLIB="$(bash "$HERE/ft_wasm_lib.sh")"
  CFLAGS+=(-I "$ROOT/build/ft_mt/src/include")
  FT_OBJS=("$ROOT"/src/gui_ft.c "$ROOT"/src/gui_ft_wasm.c "$FTLIB"); FT_EXPORTS=",_gui_ft_add_face,_gui_ft_add_alias,_malloc,_free"
fi
SHIM=("$ROOT"/src/gui_platform.c "$ROOT"/src/gui_reach.c "$BUILD"/gui_reach_tab.c)
if [ "$VARIANT" = reach ]; then
  mkdir -p "$OUT/obj"; OBJS=()
  for f in "$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c "$BUILD"/gui_stubs.c; do
    RF=(); [ "$(basename "$f")" = gui_core.c ] && RF=(-DGUI_REACH_LOG)   # WM_PAINT 配送の GUI-MSG 行 (#3510)
    o="$OUT/obj/$(basename "$f" .c).o"; emcc -c "${CFLAGS[@]}" ${RF[@]+"${RF[@]}"} -include "$BUILD/gui_rename.h" "$f" -o "$o"; OBJS+=("$o")
  done
  SHIM+=("$BUILD"/gui_wrap_i64.c "${OBJS[@]}")
else
  SHIM+=("$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c "$BUILD"/gui_stubs.c)
fi
emcc "${CFLAGS[@]}" "$LIFTED" "$ROOT/lift/gui_lift_main.c" "${SHIM[@]}" ${FT_OBJS[@]+"${FT_OBJS[@]}"} -lm \
  -sGLOBAL_BASE=1048576 -sPROXY_TO_PTHREAD=1 -sPTHREAD_POOL_SIZE=2 -sEXIT_RUNTIME=1 "${MEMFLAGS[@]}" \
  -sMODULARIZE=1 -sEXPORT_NAME=createGuiApp -sENVIRONMENT=web,worker -sERROR_ON_UNDEFINED_SYMBOLS=1 \
  -sEXPORTED_FUNCTIONS=_main,_gui_shared_ptr,_gui_shared_size,_gui_reach_dump,_gui_reach_json,_gui_reach_distinct,_gui_hostcall_ptr${FT_EXPORTS} -sEXPORTED_RUNTIME_METHODS=wasmMemory,HEAPU8 \
  -o "$OUT/app.js"
ls -la "$OUT/app.js" "$OUT/app.wasm"
