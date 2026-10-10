#!/usr/bin/env bash
# gui shim の native 単体テスト (gcc + headless host)。exit 0 = 全 PASS。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; BUILD="$ROOT/build"; mkdir -p "$BUILD"
python3 "$ROOT/gen_api.py" >/dev/null
gcc -O1 -g -w -fsanitize=address,undefined -fno-sanitize-recover=undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$BUILD" \
  "$ROOT"/src/gui_platform.c "$ROOT"/src/gui_reach.c "$BUILD"/gui_reach_tab.c "$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c "$ROOT"/src/gui_headless.c "$BUILD"/gui_stubs.c \
  "$HERE/selftest.c" -o "$BUILD/selftest" -lm
"$BUILD/selftest"
