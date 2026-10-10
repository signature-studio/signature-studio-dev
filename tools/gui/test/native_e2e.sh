#!/usr/bin/env bash
# PE(mingw) -> RetDec -> 後処理 -> gcc native + shim + headless host -> golden 比較 (wasm/chrome 不要の開発ループ)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; BUILD="$ROOT/build"; mkdir -p "$BUILD/lift"
python3 "$ROOT/gen_api.py" >/dev/null
python3 "$ROOT/golden/gen_golden.py" >/dev/null
bash "$ROOT/lift/gui_lift.sh" "$HERE/gui_app.c" "$BUILD/lift"
gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD" \
  -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=int-to-pointer-cast \
  "$BUILD/lift/lifted.c" -c -o "$BUILD/lift/lifted.o"
gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$BUILD" -Dmain=gui_lift_app_main -c "$ROOT/lift/gui_lift_main.c" -o "$BUILD/lift/lift_main.o"
gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD" \
  "$BUILD/lift/lifted.o" "$BUILD/lift/lift_main.o" "$ROOT"/src/gui_platform.c "$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c \
  "$ROOT"/src/gui_headless.c "$BUILD"/gui_stubs.c "$HERE/native_run.c" -o "$BUILD/native_run" -lm
(cd "$BUILD" && ./native_run "$ROOT/golden/final.ppm" "$BUILD/native_actual.ppm")
