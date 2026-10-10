#!/usr/bin/env bash
# gui_wasm.sh — lifted.c + shim を emcc で wasm (pthread, SAB) 化。usage: gui_wasm.sh <lifted.c> <outdir>
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; BUILD="$ROOT/build"
LIFTED="$1"; OUT="$2"; VARIANT="${3:-fixed}"; mkdir -p "$OUT"
# fixed: 128MB 固定 / grow: 3MB 初期 + ALLOW_MEMORY_GROWTH (メモリ成長時に worker が memory.buffer を取り直せることの検証用)
if [ "$VARIANT" = grow ]; then MEMFLAGS=(-sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=3145728 -sMAXIMUM_MEMORY=1073741824 -sSTACK_SIZE=524288)
else MEMFLAGS=(-sINITIAL_MEMORY=134217728 -sSTACK_SIZE=1048576); fi
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
command -v emcc >/dev/null || { echo "emcc not found" >&2; exit 2; }
python3 "$ROOT/gen_api.py" >/dev/null
# 定型: tools/m1/flags.sh の CLANG_FLAGS 系に準拠 (lifter 産 C 向けに -w/-Wno-error=int-conversion, -fwrapv)
emcc -O1 -fwrapv -w -fno-strict-aliasing -pthread \
  -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=int-to-pointer-cast -Wno-error=implicit-function-declaration \
  -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD" \
  "$LIFTED" "$ROOT/lift/gui_lift_main.c" "$ROOT"/src/gui_platform.c "$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c "$BUILD"/gui_stubs.c \
  -sGLOBAL_BASE=1048576 -sPROXY_TO_PTHREAD=1 -sPTHREAD_POOL_SIZE=2 -sEXIT_RUNTIME=1 "${MEMFLAGS[@]}" \
  -sMODULARIZE=1 -sEXPORT_NAME=createGuiApp -sENVIRONMENT=web,worker -sERROR_ON_UNDEFINED_SYMBOLS=1 \
  -sEXPORTED_FUNCTIONS=_main,_gui_shared_ptr,_gui_shared_size -sEXPORTED_RUNTIME_METHODS=wasmMemory,HEAPU8 \
  -o "$OUT/app.js"
ls -la "$OUT/app.js" "$OUT/app.wasm"
