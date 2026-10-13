#!/usr/bin/env bash
# nc_golden.sh — GUI-7 (#183): popup/tooltip surface・NC 領域・無効領域複数矩形・DPI の golden (独立 Python オラクル) + ネガコン 3 本。
# ネガコン (期待値 1 画素改変 / tooltip の z-order 欠陥 / 単一矩形化の欠陥) は **FAIL しなければ** このスクリプトが exit 1。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; B="$ROOT/build"; mkdir -p "$B"
python3 "$ROOT/gen_api.py" >/dev/null
gcc -O1 -g -w -fsanitize=address,undefined -fno-sanitize-recover=undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$B" \
  "$ROOT"/src/gui_platform.c "$ROOT"/src/gui_reach.c "$B"/gui_reach_tab.c "$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c "$ROOT"/src/gui_headless.c "$B"/gui_stubs.c \
  "$HERE/nc_golden.c" -o "$B/nc_golden" -lm
"$B/nc_golden" "$B/nc_scene.ppm"
python3 "$ROOT/golden/gen_golden_nc.py" "$B/nc_scene.ppm"
fail=0
if python3 "$ROOT/golden/gen_golden_nc.py" "$B/nc_scene.ppm" --tamper >/dev/null 2>&1; then echo "NEGCTL FAIL: tampered golden was accepted"; fail=1; else echo "negctl 1/3 OK: tampered golden (1 px) rejected"; fi
for f in 1 2; do
  NC_FAULT=$f "$B/nc_golden" "$B/nc_scene_f$f.ppm" >"$B/nc_f$f.out" 2>&1 || true
  if python3 "$ROOT/golden/gen_golden_nc.py" "$B/nc_scene_f$f.ppm" >"$B/nc_f$f.cmp" 2>&1; then echo "NEGCTL FAIL: NC_FAULT=$f was accepted"; fail=1; else echo "negctl $((f+1))/3 OK: NC_FAULT=$f rejected ($(cut -c1-50 "$B/nc_f$f.cmp"))"; fi
done
[ "$fail" = 0 ] && echo "[nc-golden] ALL PASS" || { echo "[nc-golden] FAILED"; exit 1; }
