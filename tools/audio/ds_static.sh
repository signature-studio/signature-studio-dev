#!/usr/bin/env bash
# FL の DirectSound バッファ形式・呼出面の静的確認 (AU-4 #189) → results/ds_static.txt
# 使い方: bash tools/audio/ds_static.sh   (FL_WIN64_DIR は tools/shared/env.sh、pefile/capstone が必要: uv pip install pefile capstone)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
. "$HERE/../shared/env.sh"
PY="${PYTHON:-python3}"
mkdir -p "$HERE/results"
"$PY" "$HERE/fl_ds_surface.py" > "$HERE/results/ds_static.txt"
echo "[audio] ds_static -> $HERE/results/ds_static.txt ($(wc -l < "$HERE/results/ds_static.txt") lines)"
