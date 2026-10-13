#!/usr/bin/env bash
# native 実機械語 (OTT_vst2_win64.dll) の processReplacing(128f) を計時。 前提: bash tools/ott/ott_e2e.sh 実行済み (tools/ott/work/libottnative.so)
#   bash tools/perf/native/native_bench.sh [reps=5] [iters=20000]   → JSON を reps 行 (署名 6b1696f0 は wasm 版と一致すべき)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../../shared/env.sh"
LIB="$HERE/../../ott/work/libottnative.so"; DLL="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"
[ -f "$LIB" ] || { echo "[native_bench] $LIB 無し (bash tools/ott/ott_e2e.sh を先に)" >&2; exit 2; }
mkdir -p "$HERE/../work"; BIN="$HERE/../work/native_bench"
gcc -O2 -o "$BIN" "$HERE/native_bench.c" -ldl -lm
for _ in $(seq 1 "${1:-5}"); do setarch x86_64 -R "$BIN" "$DLL" "$LIB" "${2:-20000}"; done
