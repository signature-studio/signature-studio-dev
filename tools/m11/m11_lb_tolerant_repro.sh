#!/usr/bin/env bash
# M11 LB 依存差の再現 (#3188): lift 成果物 (work/boot0..4.lift.ll) から後段だけを回し、寛容起動 (m11_tolerant.mjs) の unit 別結果を取る。
#   使い方: bash tools/m11/m11_lb_tolerant_repro.sh <LB 0|0x10000> <出力先 (tools/m11/ 基準の相対 path)>
#   例:    bash tools/m11/m11_lb_tolerant_repro.sh 0 work/repro_lb0
#   出力:  <出力先>/tolerant_units.json (寛容起動の全 unit 記録), <出力先>/tolerant.out (M11_TOLERANT 行)
#   m11_e2e.sh の全再生成 (lift_pe.sha256 の指紋検査) は通らない (work-m11 は #516 以前の snapshot) ので使わない。
#   PE は FL_WIN64_DIR 経由 (tools/shared/env.sh)。work/ は gitignore (commit しない)。
set -euo pipefail
cd "$(dirname "$0")"
source ../shared/env.sh
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
LB="${1:?LB 0|0x10000}"
OUT="${2:?出力先 (例 work/repro_lb0)}"
export M11_LB_BASE="$LB"
PE="${M11_PE:-${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}}"
export PE M11_PE="$PE"
[ -f "$PE" ] || { echo "[lbrepro] PE 無し: $PE (FL_WIN64_DIR を設定する)" >&2; exit 1; }
mkdir -p "$OUT"
step() { echo "[lbrepro LB=$LB] $*"; }
step "gen_ir2 (IR 再生成)"
bash m11_gen_ir2.sh > "$OUT/gen.log" 2>&1
echo "$LB" > work/ir_lb_base.stamp
echo "$LB" > work/img_lb_base.stamp
rm -f work/m11_data.c work/m11_image.bin
step "data / image / lb_check"
python3 m11_data_gen.py "$PE" > "$OUT/data.log" 2>&1
python3 m11_image_gen.py "$PE" > "$OUT/image.log" 2>&1
python3 lb_check.py "$PE" work/m11_image.bin "$LB" > "$OUT/lb_check.log" 2>&1
step "build (emcc)"
bash m11_build.sh > "$OUT/build.log" 2>&1
[ -f work/m11_boot.cjs.wasm ] || { step "wasm 未生成: $OUT/build.log"; exit 1; }
cp work/ir_conditions.json "$OUT/ir_conditions.json"
cp work/boot_final.ll "$OUT/boot_final.ll"
step "寛容起動 (m11_tolerant.mjs)"
M11_TOLERANT_OUT="$OUT/tolerant_units.json" timeout 600 node m11_tolerant.mjs > "$OUT/tolerant.out" 2>&1 || true
grep '^M11_TOLERANT ' "$OUT/tolerant.out" | cut -c1-400 || true
