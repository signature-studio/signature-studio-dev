#!/usr/bin/env bash
# PY-264 (#3888) 受入 2: py264_arith_scan.py を全 PE block に並列で当てる (block ごとに timeout 付き)。
#   FL_WIN64_DIR=<展開先> bash analysis/py264_arith_scan_all.sh <出力dir> [並列数=4] [block名の部分一致]
# 展開先の extracted/*_PE.bin を走査する。出力は <出力dir>/<block>.txt (末尾に rc=N)。
# 集計: grep -h '^rc=' <出力dir>/*.txt | sort | uniq -c   /   grep -h vptr <出力dir>/*.txt
set -u
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:?出力 dir を指定}"
par="${2:-4}"
filt="${3:-}"
ext="$FL_WIN64_DIR/extracted"
mkdir -p "$out"
for f in "$ext"/*_PE.bin; do basename "$f"; done | grep -- "$filt" |
  xargs -P "$par" -I{} sh -c \
    'FL_WIN64_DIR="$0" timeout 900 python3 "$1/py264_arith_scan.py" "$2" > "$3/$2.txt" 2>&1; echo "rc=$?" >> "$3/$2.txt"' \
    "$FL_WIN64_DIR" "$here" {} "$out"
