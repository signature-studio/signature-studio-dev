#!/usr/bin/env bash
# CAB-156 native 検証: (1) 到達 API ログ (wrapper 経路) (2) wasm32 署名 adapter の wiring + ハンドル 31bit (3) 改名ビルドで selftest が通る
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; BUILD="$ROOT/build"; mkdir -p "$BUILD"
python3 "$ROOT/gen_api.py" >/dev/null
python3 "$ROOT/integ/gen_adapt.py" --no-md | tail -1
CF=(-O1 -g -w -fsanitize=address,undefined -fno-sanitize-recover=undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD")
PLAT=("$ROOT"/src/gui_platform.c "$ROOT"/src/gui_reach.c "$BUILD"/gui_reach_tab.c "$ROOT"/src/gui_headless.c)
SHIM=("$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c "$BUILD"/gui_stubs.c)
OBJ="$BUILD/reach_obj"; mkdir -p "$OBJ"
for f in "${SHIM[@]}"; do gcc -c "${CF[@]}" -include "$BUILD/gui_rename.h" "$f" -o "$OBJ/$(basename "$f" .c).o"; done
gcc "${CF[@]}" "${PLAT[@]}" "$OBJ"/*.o "$BUILD/gui_wrap_i64.c" "$HERE/reach_test.c" -o "$BUILD/reach_test" -lm
"$BUILD/reach_test" 2>/dev/null | tail -3
gcc "${CF[@]}" -DGUI_REACH_LOG "${PLAT[@]}" "$OBJ"/*.o "$BUILD/gui_adapt_w32.c" "$HERE/adapt_test.c" -o "$BUILD/adapt_test" -lm
"$BUILD/adapt_test" 2>/dev/null | tail -3
# 改名 + wrapper ビルドでも既存 selftest が全 PASS (wrapper が挙動を変えない)
gcc "${CF[@]}" "${PLAT[@]}" "$OBJ"/*.o "$BUILD/gui_wrap_i64.c" "$HERE/selftest.c" -o "$BUILD/selftest_wrapped" -lm
"$BUILD/selftest_wrapped" 2>/dev/null | tail -1
