#!/usr/bin/env bash
# #4498 受入 5: 1046a30 の VA remap (M11_M2R) の before/after を unit 実行で比べる。
#   既定 (M11_M2R 未設定) と M11_M2R=1 で、IR 生成 → build → 通常起動 / survey / 寛容起動 を走らせ、結果 (JSON 行) と IR 差分行数を並べる。
#   m11_e2e.sh 全体 (lift 再生成・judge) は回さない。前提: work/ に lift 成果物 (boot0〜4.lift.ll) と PE (FL_WIN64_DIR) があること。
#   出力: work/unit_4498/{default,m2r1}/ (work/ の下なので commit しない)
set -euo pipefail
cd "$(dirname "$0")/.."
source ../shared/env.sh   # FL_WIN64_DIR
export PE="${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
OUT=work/unit_4498
rm -rf "$OUT"; mkdir -p "$OUT/default" "$OUT/m2r1"
run_one() {  # run_one <name> <M11_M2R 値 (0 は未設定扱い)>
  local name="$1" m2r="$2" d="$OUT/$1"
  if [ "$m2r" = 1 ]; then export M11_M2R=1; else unset M11_M2R; fi
  bash m11_gen_ir2.sh > "$d/gen.log" 2>&1
  cp work/boot_final.ll "$d/boot_final.ll"; sha256sum "$d/boot_final.ll" | cut -c1-16 > "$d/ir_sha.txt"
  bash m11_build.sh > "$d/build.log" 2>&1
  python3 m11_data_gen.py "$PE" > "$d/data.log" 2>&1
  python3 m11_image_gen.py "$PE" > "$d/image.log" 2>&1
  python3 lb_check.py "$PE" work/m11_image.bin 0 > "$d/lb.log" 2>&1
  timeout 300 node m11_run.mjs > "$d/run.out" 2>&1 || true
  timeout 600 node m11_survey.mjs > "$d/survey.out" 2>&1 || true
  M11_TOLERANT_OUT="$d/tolerant.json" timeout 600 node m11_tolerant.mjs > "$d/tolerant.out" 2>&1 || true
}
run_one default 0
run_one m2r1 1
unset M11_M2R
{
  echo "IR sha256 (16 桁): default=$(cat $OUT/default/ir_sha.txt) m2r1=$(cat $OUT/m2r1/ir_sha.txt)"
  echo "IR 差分行数 (diff の変更行): $(diff "$OUT/default/boot_final.ll" "$OUT/m2r1/boot_final.ll" | grep -c '^[<>]' || true)"
  for f in run survey tolerant; do
    for d in default m2r1; do
      echo "$f $d: $(grep -oE 'M11_(RESULT|SURVEY|TOLERANT) .*' "$OUT/$d/$f.out" | head -1 | sed -E 's/"va_[a-z_]+":[0-9]+,//g' | cut -c1-120)"
    done
  done
} | tee "$OUT/summary.txt"
