#!/usr/bin/env bash
# gui_lift.sh — mingw-w64 で PE32+ をビルド → RetDec で lift → 後処理 (lifted.c) まで。tools/m1 の PE→RetDec 段に相当。
#   usage: gui_lift.sh <app.c> <outdir> [WndProcName...]   (WndProc 名は省略可: 後処理が自動検出する)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
SRC="$1"; OUT="$2"; shift 2
WNDPROCS=("$@")
mkdir -p "$OUT"
command -v x86_64-w64-mingw32-gcc >/dev/null || { echo "mingw-w64 gcc not found" >&2; exit 2; }
RETC="${RETDEC_DECOMPILER:-/opt/retdec/bin/retdec-decompiler}"
x86_64-w64-mingw32-gcc -O0 -ffreestanding -fno-builtin -nostartfiles -nostdlib -mwindows -Wl,-e,entry \
  "$SRC" -o "$OUT/app.exe" -lkernel32 -luser32 -lgdi32
[ "$(dd if="$OUT/app.exe" bs=1 count=2 2>/dev/null)" = "MZ" ]
"$RETC" "$OUT/app.exe" -o "$OUT/retdec.c" >/dev/null 2>&1
ARGS=(); for w in ${WNDPROCS[@]+"${WNDPROCS[@]}"}; do ARGS+=(--wndproc "$w"); done
python3 "$HERE/gui_lift_post.py" "$OUT/retdec.c" "$OUT/app.exe" "$OUT/lifted.c" "${ARGS[@]}"
