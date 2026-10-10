#!/usr/bin/env bash
# classify.py の根拠検査用: mac slice 全 + win 主要ブロックの strings を work/strings に生成
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."
mkdir -p "$ROOT/work/strings"
python3 - <<PY
import sys, glob; sys.path.insert(0, "$HERE")
from common import *
for p in sorted(glob.glob(MAC_SHARED + "/*.dylib")): fat_slice(p)
fat_slice(MAC_APP + "/Contents/Libs/FLEngine_x64.dylib")
PY
for f in "$ROOT"/work/slices/*.dylib; do b=$(basename "$f" .dylib); [ -s "$ROOT/work/strings/$b.txt" ] || strings -a -n 6 "$f" > "$ROOT/work/strings/$b.txt" & done
for n in 24339 24341 24342 24345 24346 24347 24348 24350 24351 24352 24353 24354 24356 24357 24359 24360 24361 24364; do
  [ -s "$ROOT/work/strings/win_$n.txt" ] || strings -a -n 6 "/home/ubuntu/work/analysis/win64/extracted/block${n}_PE.bin" > "$ROOT/work/strings/win_$n.txt" & done
[ -s "$ROOT/work/strings/win_24351_u16.txt" ] || strings -a -el -n 6 "/home/ubuntu/work/analysis/win64/extracted/block24351_PE.bin" > "$ROOT/work/strings/win_24351_u16.txt"
wait; echo "[strings] $(ls "$ROOT/work/strings" | wc -l) files"
