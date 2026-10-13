#!/usr/bin/env bash
# bench.sh — shim の GDI 転送スループット (native -O2, 1920x1080, 30 反復/行)。usage: bench.sh [N=3] [GUI_DIR=この tools/gui]
#   GUI_DIR に別 commit の tools/gui (git archive 展開) を渡すと前後比較ができる (その場合 -DBENCH_BPP は旧実装が fail-fast のため付けない: BENCH_BPP=0)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; N="${1:-3}"; R="${2:-$HERE/..}"; BPP="${BENCH_BPP:-1}"
OUT="$(mktemp -d "${TMPDIR:-/tmp}/gui_bench.XXXXXX")"; python3 "$R/gen_api.py" >/dev/null 2>&1 || true; mkdir -p "$R/build"; python3 "$R/gen_api.py" >/dev/null
XF=(); [ "$BPP" = 1 ] && XF=(-DBENCH_BPP)
gcc -O2 -w -pthread "${XF[@]}" -I "$R/include" -I "$R/src" -I "$R/build" "$R"/src/gui_platform.c "$R"/src/gui_reach.c "$R"/build/gui_reach_tab.c "$R"/src/gui_core.c "$R"/src/gui_gdi.c "$R"/src/gui_headless.c "$R"/build/gui_stubs.c "$HERE/bench.c" -o "$OUT/bench" -lm
echo "[bench] gcc $(gcc -dumpversion), $(nproc) CPU, load(1m) $(cut -d' ' -f1 /proc/loadavg), $N runs"
for i in $(seq 1 "$N"); do "$OUT/bench"; done
rm -rf "$OUT"
