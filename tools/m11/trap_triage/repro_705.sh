#!/usr/bin/env bash
# #944: function_413060 (D4) の OFF 実害測定の再現。OFF (lift 版) と ON (M11_OV_413060=1, C 転記版) の survey を直列・単発で 1 回ずつ実行し,
# 各回の所要時間・load・集計 (ok/noproc/miss/trap/clobber)・function_413060 の到達計数 (unit 数・呼出し数) を出す。
# 前提: work/ が m11_e2e.sh 相当で生成済み (work/boot_final.ll・work/ir_conditions.json)、FL_WIN64_DIR 設定済み。
# 使い方: bash tools/m11/trap_triage/repro_705.sh
set -u
cd "$(dirname "$0")/.."   # tools/m11 へ
export FL_WIN64_DIR="${FL_WIN64_DIR:-}"
OUT=work/repro_705; mkdir -p "$OUT"
run_one() {  # run_one <label> <M11_OV_413060 値>
  local label="$1" gate="$2"
  M11_OV_413060="$gate" timeout 300 bash m11_build.sh > "$OUT/build_$label.log" 2>&1 || { echo "[repro_705] build $label FAILED"; return 1; }
  local t0 t1
  t0=$(date +%s.%N)
  M11_SURVEY_UNITS="$OUT/units_$label.json" timeout 300 node m11_survey.mjs > "$OUT/survey_$label.out" 2>/dev/null; local rc=$?
  t1=$(date +%s.%N)
  echo "[repro_705] $label: rc=$rc elapsed=$(echo "$t1 - $t0" | bc) s load=$(cut -d' ' -f1 /proc/loadavg)"
  grep -o '"ok":[0-9]*\|"noproc":[0-9]*\|"miss":[0-9]*\|"trap":[0-9]*\|"clobber":[0-9]*\|"f413060_calls":[0-9]*' "$OUT/survey_$label.out" | tr '\n' ' '; echo
}
run_one off 0
run_one on 1
python3 - "$OUT" <<'EOF'
import json, sys
d = sys.argv[1]
o = json.load(open(f'{d}/units_off.json')); n = json.load(open(f'{d}/units_on.json'))
diff = [i for i in range(len(o)) if o[i] != n[i]]
print(f'[repro_705] unit ラベルの OFF/ON 差分: {len(diff)} unit {diff[:20]}')
EOF
