#!/usr/bin/env bash
# bpp_golden.sh — GUI-5 (#181): 各 bpp シーンを shim で描画し、独立 Python オラクル (golden/gen_golden_bpp.py) と画素完全一致を検査する。
# ネガティブコントロール 2 本 (期待値を 1 画素壊す / shim 側に故意の欠陥 BPP_FAULT=1) は **FAIL(exit 1) しなければ** このスクリプトが exit 1。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; B="$ROOT/build"; mkdir -p "$B"
python3 "$ROOT/gen_api.py" >/dev/null
gcc -O1 -g -w -fsanitize=address,undefined -fno-sanitize-recover=undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$B" \
  "$ROOT"/src/gui_platform.c "$ROOT"/src/gui_reach.c "$B"/gui_reach_tab.c "$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c "$ROOT"/src/gui_headless.c "$B"/gui_stubs.c \
  "$HERE/bpp_golden.c" -o "$B/bpp_golden" -lm
"$B/bpp_golden" "$B/bpp_scene.ppm" >/dev/null
python3 "$ROOT/golden/gen_golden_bpp.py" "$B/bpp_scene.ppm"
fail=0
if python3 "$ROOT/golden/gen_golden_bpp.py" "$B/bpp_scene.ppm" --tamper >/dev/null 2>&1; then echo "NEGCTL FAIL: tampered golden was accepted"; fail=1; else echo "negctl 1/2 OK: tampered golden (1 px) rejected"; fi
BPP_FAULT=1 "$B/bpp_golden" "$B/bpp_scene_fault.ppm" >/dev/null
if python3 "$ROOT/golden/gen_golden_bpp.py" "$B/bpp_scene_fault.ppm" >"$B/bpp_fault.out" 2>&1; then echo "NEGCTL FAIL: shim with injected palette fault was accepted"; fail=1; else echo "negctl 2/2 OK: injected fault rejected ($(cut -c1-60 "$B/bpp_fault.out"))"; fi
[ "$fail" = 0 ] && echo "[bpp-golden] ALL PASS" || { echo "[bpp-golden] FAILED"; exit 1; }
