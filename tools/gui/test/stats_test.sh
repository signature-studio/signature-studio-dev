#!/usr/bin/env bash
# stats_test.sh — headless surface 統計 (gui_hl_stats) と SHA-256 の単体テスト + ネガコン (#3460 受入 2)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; BUILD="$ROOT/build"; mkdir -p "$BUILD"
gcc -O1 -g -Wall -fsanitize=address,undefined -I "$ROOT/src" "$HERE/stats_test.c" "$ROOT/src/gui_hl_stats.c" -o "$BUILD/stats_test"
"$BUILD/stats_test"
