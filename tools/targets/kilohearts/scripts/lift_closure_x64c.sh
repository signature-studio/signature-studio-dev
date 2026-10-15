#!/usr/bin/env bash
# KH-38 (#3065): 対照 Gain の before 160 関数 closure を flelift の x64c で lift し、unsup の件数を出す。
# usage: lift_closure_x64c.sh <HeartCore.core_64> <out_dir>
#   X64C=<path> で lifter を差し替え可 (既定 = tools/flelift/x64c.py。before 測定は origin/main 版を指定)。
# 素材: plugins-kilohearts → Kilohearts Offline Installer.zip → payload.dat → windows.zip/* → HeartCore.core_64 (REPORT_KH19.md §9)。
set -euo pipefail
CORE="${1:?HeartCore.core_64 のパス}"
OUT="${2:?出力ディレクトリ}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
X64C="${X64C:-$ROOT/tools/flelift/x64c.py}"
mkdir -p "$OUT"
python3 - "$HERE/../gain_before_160.tsv" "$OUT/entries.json" <<'EOF'
import csv, json, sys
rows = list(csv.DictReader(open(sys.argv[1]), delimiter='\t'))
IMG = 0x180000000
json.dump({'roots': [IMG + int(r['func_rva'], 16) for r in rows if r['root_class']],
           'calltgt': [int(r['func_rva'], 16) for r in rows]}, open(sys.argv[2], 'w'))
EOF
python3 "$X64C" --pe "$CORE" --entries "$OUT/entries.json" --out "$OUT/lift" --closure 0 \
  --img 0x180000000 --shift 0 --img-size 0x625c000 --impbase 0x1D80000
echo "lifter=$X64C"
python3 - "$OUT/lift/lift_meta.json" <<'EOF'
import json, sys
m = json.load(open(sys.argv[1]))
print('unsup kinds=%d sites=%d functions=%d' % (len(m['unsup']), sum(m['unsup'].values()), len(m['functions'])))
EOF
