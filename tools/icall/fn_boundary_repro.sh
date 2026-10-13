#!/usr/bin/env bash
# fn_boundary_repro.sh — #851: 0x128c320 の関数境界誤認 (1 バイト関数化) の再現 (リポジトリ単独で動く範囲)
#   FL_WIN64_DIR=<fl-win64 展開先> bash tools/icall/fn_boundary_repro.sh <outdir>
#   必要素材: fl-win64 (block00031_PE.bin), toolchain-retdec (RETDEC=<retdec-decompiler の絶対パス> を指定)
#   (1) 最小範囲 A = 隣接 0x128c280 と本体 0x128c320 のみ / B = A + 0x128c2f0 (無選択の隣接関数)
#   (2) 2 関数のみ C = 呼出元 0x128f9e0 と 0xc589b0 のみ / D = C + 0x128c320 本体
#   (3) 任意: RANGES_DIR に before.ranges.N (rt_flengine の分割範囲, work/ 由来) があれば N=0..3 を decode
# 各 run の集計 (decode log から): rc / NonRecursiveCFGBuilder の行数 (grep -c) / function_128c320 のラベル / 所要秒
# 判定: 本体を含む A/B/D では 0x128c320--0x128dc44 (正)、C では 0x128c320--0x128c321 (1 B) になるなら、原因は範囲分割。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
PE="${FL_WIN64_DIR:?FL_WIN64_DIR を設定 (fl-win64 展開先)}/extracted/block00031_PE.bin"
OUT="${1:?outdir を指定}"
RETDEC="${RETDEC:?RETDEC を設定 (toolchain-retdec の retdec-decompiler)}"
RANGES_DIR="${RANGES_DIR:-}"
[[ -f "$PE" ]] || { echo "PE が無い: $PE (fl-win64 を展開)"; exit 2; }
[[ -x "$RETDEC" ]] || { echo "RetDec が無い: $RETDEC (toolchain-retdec を展開するか RETDEC= を指定)"; exit 2; }
mkdir -p "$OUT"
export TMPDIR="$OUT"
label() { grep -h "^; function: function_128c320 at" "$1" 2>/dev/null | sed 's/^; function: //'; }
run() {  # $1 name $2 ranges
  local s rc
  s=$(date +%s)
  timeout 110 "$RETDEC" "$PE" -o "$OUT/$1.drc.c" --select-ranges "$2" --select-decode-only --timeout 100 > "$OUT/$1.log" 2>&1
  rc=$?
  echo "[$1] rc=$rc sec=$(( $(date +%s) - s )) NonRecursive=$(grep -c NonRecursiveCFGBuilder "$OUT/$1.log") $(label "$OUT/$1.drc.dsm")"
}
run A "0x128c280-0x128c2e1,0x128c320-0x128dc44"
run B "0x128c280-0x128c2e1,0x128c2f0-0x128c313,0x128c320-0x128dc44"
run C "0xc589b0-0xc5d667,0x128f9e0-0x1294ab8"
run D "0xc589b0-0xc5d667,0x128f9e0-0x1294ab8,0x128c320-0x128dc44"
if [[ -n "$RANGES_DIR" && -f "$RANGES_DIR/before.ranges.0" ]]; then
  for i in 0 1 2 3; do
    run chunk$i "$(cat "$RANGES_DIR/before.ranges.$i")" || true
  done
else
  echo "[chunk] skipped: RANGES_DIR 未指定 (before.ranges.N は roundtrip.sh の work/ 出力でリポジトリ外)"
fi
