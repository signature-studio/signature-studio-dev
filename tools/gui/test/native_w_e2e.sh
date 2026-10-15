#!/usr/bin/env bash
# native_w_e2e.sh — W 版ゲスト (gui_app_w.c: RegisterClassW → CreateWindowExW → メッセージループ → WM_PAINT → GDI → W 文字列往復)
#   を mingw PE → RetDec → 後処理 → gcc native + shim + headless host で走らせ、最終 surface の統計を取る (#3460)。
#   FL の素材は使わない (fl-win64 不要)。出力 PPM は build/ (gitignore) に置く。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; BUILD="$ROOT/build"; mkdir -p "$BUILD/lift_w"
python3 "$ROOT/gen_api.py" >/dev/null
bash "$ROOT/lift/gui_lift.sh" "$HERE/gui_app_w.c" "$BUILD/lift_w" WndProc SubWndProc
gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD" \
  -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=int-to-pointer-cast \
  "$BUILD/lift_w/lifted.c" -c -o "$BUILD/lift_w/lifted.o"
gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$BUILD" -Dmain=gui_lift_app_main -c "$ROOT/lift/gui_lift_main.c" -o "$BUILD/lift_w/lift_main.o"
gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD" \
  "$BUILD/lift_w/lifted.o" "$BUILD/lift_w/lift_main.o" "$ROOT"/src/gui_platform.c "$ROOT"/src/gui_reach.c "$BUILD"/gui_reach_tab.c "$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c \
  "$ROOT"/src/gui_headless.c "$ROOT"/src/gui_hl_stats.c "$BUILD"/gui_stubs.c "$HERE/native_w_run.c" -o "$BUILD/native_w_run" -lm
(cd "$BUILD" && ./native_w_run "$BUILD/w_actual.ppm")
