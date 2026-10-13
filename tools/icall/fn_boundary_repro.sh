#!/usr/bin/env bash
# fn_boundary_repro.sh — #851: 0x128c320 の関数境界誤認 (1 バイト関数化) の再現
#   bash tools/icall/fn_boundary_repro.sh <outdir>
#   (1) 最小範囲 A = 隣接 0x128c280 と本体 0x128c320 のみ / B = A + 0x128c2f0 (無選択の隣接関数)
#   (2) 分割 decode: rt_flengine の before.ranges.N を N=0..3 で decode し、0x128c320 のラベルを集計
# 判定: 最小範囲では本体 (--0x128dc44)、分割 chunk では 1 バイト (--0x128c321) になるなら、原因は範囲分割。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
PE="${FL_WIN64_DIR:?FL_WIN64_DIR を設定 (fl-win64 展開先)}/extracted/block00031_PE.bin"
OUT="${1:?outdir を指定}"
RANGES_DIR="${RANGES_DIR:-$HERE/work/rt_flengine}"
mkdir -p "$OUT"
export TMPDIR="$OUT"
label() { grep -h "^; function: function_128c320 at" "$1" 2>/dev/null | sed 's/^; function: //'; }
run() {  # $1 name $2 ranges
  timeout 110 /opt/retdec/bin/retdec-decompiler "$PE" -o "$OUT/$1.drc.c" --select-ranges "$2" --select-decode-only --timeout 100 > "$OUT/$1.log" 2>&1
  echo "[$1] rc=$? $(label "$OUT/$1.drc.dsm")"
}
run A "0x128c280-0x128c2e1,0x128c320-0x128dc44"
run B "0x128c280-0x128c2e1,0x128c2f0-0x128c313,0x128c320-0x128dc44"
for i in 0 1 2 3; do
  run chunk$i "$(cat "$RANGES_DIR/before.ranges.$i")" || true
done
