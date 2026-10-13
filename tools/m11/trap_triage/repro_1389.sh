#!/usr/bin/env bash
# #1389 (親 #1149): function_413060 の dest 書込み値を OFF (lift 版) と ON (C 転記版) で呼出し単位に比較する。
# 指紋 (dest_obs_hash) はポインタ値を含むためヒープ配置の差 (ビルド差) で揺れる。ここでは呼出し k ごとに
# 文字列の内容 (長さ・UTF-16 本体の FNV) と refcount を記録し、k と unit (VA) で突き合わせる。
# 手順: OFF → OFF 再実行 (決定性) → ON を直列・単発で実行し、tools/m11/trap_triage/cmp_1389.py で比較する。
# 前提: work/ir_conditions.json 生成済み (m11_gen_ir2.sh)、FL_WIN64_DIR 設定済み、PATH に agent-py venv。
# 使い方: bash tools/m11/trap_triage/repro_1389.sh
set -u
cd "$(dirname "$0")/.."   # tools/m11 へ
export FL_WIN64_DIR="${FL_WIN64_DIR:-}"
OUT=work/repro_1389; mkdir -p "$OUT"
FAIL=0
run_one() {  # run_one <label> <M11_OV_413060 値>
  local label="$1" gate="$2" t0 t1 rc
  if ! M11_INSTR_413060=1 M11_OV_413060="$gate" M11_NEG_413060=0 timeout 300 bash m11_build.sh > "$OUT/build_$label.log" 2>&1; then
    echo "[repro_1389] build $label FAILED"; FAIL=1; return 1
  fi
  t0=$(date +%s%N)
  M11_INSTR_413060=1 M11_DEST_REC_OUT="$OUT/rec_$label.json" M11_SURVEY_COST="$OUT/cost_$label.json" timeout 300 node m11_survey.mjs > "$OUT/survey_$label.out" 2>/dev/null; rc=$?
  t1=$(date +%s%N)
  echo "[repro_1389] $label: rc=$rc elapsed=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.3f", (b-a)/1e9}') s load=$(cut -d' ' -f1 /proc/loadavg)"
  if [ "$rc" -ne 0 ]; then echo "[repro_1389] survey $label FAILED (rc=$rc)"; FAIL=1; return 1; fi
  grep '^M11_SURVEY ' "$OUT/survey_$label.out" | cut -c1-240
}
run_one off 0
run_one off2 0
run_one on 1
python3 trap_triage/cmp_1389.py "$OUT" || FAIL=1
echo "[repro_1389] $([ "$FAIL" -eq 0 ] && echo PASS || echo FAIL)"
exit "$FAIL"
