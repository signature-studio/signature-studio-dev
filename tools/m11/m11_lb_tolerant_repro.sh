#!/usr/bin/env bash
# M11 寛容起動 (m11_tolerant.mjs) の LB 別再現 (#3160): IR 生成 → 画像 → 静的検査 → build → 寛容起動 (942 unit) を 1 LB ぶん実行する.
#   使い方: bash tools/m11/m11_lb_tolerant_repro.sh <LB> <出力ディレクトリ>   (例: 0 work/lb0 / 0x10000 work/lb10000)
#   前提: fl-win64 を FL_WIN64_DIR に展開済み・work-m11 を tools/m11/work に展開済み・/opt/emsdk・python の pefile と capstone.
#   m11_e2e.sh の全再生成は使わない (work-m11 に work/lift_pe.sha256 が無く全再生成に入るため)。lift 成果物 (boot*.lift.ll) から後段だけを実行する.
#   注意: work/boot_final.ll・work/m11_boot.cjs・work/m11_image.bin を上書きする (LB ごとに作り直す)。
set -u
cd "$(dirname "$0")"
source ../shared/env.sh   # FL_WIN64_DIR
LB="${1:?LB (0 or 0x10000)}"
OUT="${2:?出力ディレクトリ}"
export M11_LB_BASE="$LB"
export PE="${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
export M11_PE="$PE"
mkdir -p "$OUT" work
rm -f work/m11_data.c work/m11_image.bin
echo "$LB" > work/ir_lb_base.stamp
echo "$LB" > work/img_lb_base.stamp
bash m11_gen_ir2.sh > "$OUT/gen_ir2.log" 2>&1 || { echo "gen_ir2 FAIL (fail-closed): $OUT/gen_ir2.log"; exit 1; }
python3 m11_data_gen.py "$PE" > "$OUT/data.log" 2>&1 && python3 m11_image_gen.py "$PE" > "$OUT/image.log" 2>&1 || { echo "image FAIL"; exit 1; }
python3 lb_check.py "$PE" work/m11_image.bin "$LB" > "$OUT/lb_check.log" 2>&1 || { echo "lb_check FAIL: $OUT/lb_check.log"; exit 1; }
bash m11_build.sh > "$OUT/build.log" 2>&1 || { echo "build FAIL: $OUT/build.log"; exit 1; }
t0=$(date +%s%N)
M11_TOLERANT_OUT="$OUT/tolerant_units.json" timeout 600 node m11_tolerant.mjs > "$OUT/tolerant.out" 2>&1; rc=$?
t1=$(date +%s%N)
echo "LB=$LB tolerant rc=$rc wall_ms=$(( (t1 - t0) / 1000000 ))"
grep '^M11_TOLERANT ' "$OUT/tolerant.out" | cut -c1-600
