#!/usr/bin/env bash
# #944: function_413060 (D4) の OFF 実害測定の再現。OFF (lift 版) と ON (M11_OV_413060=1, C 転記版) の survey を直列・単発で 1 回ずつ実行し,
# 各回の所要時間・load・集計 (ok/noproc/miss/trap/clobber)・function_413060 の到達計数 (unit 数・呼出し数) を出す。
# 判定: build / survey の rc≠0、unit ラベルの OFF/ON 差分あり、計数 (ok/noproc/miss/trap/clobber/f413060_calls) の不一致 のいずれかで FAIL (exit 1)。
# 前提: work/ が m11_e2e.sh 相当で生成済み (work/boot_final.ll・work/ir_conditions.json)、FL_WIN64_DIR 設定済み。
# 使い方: bash tools/m11/trap_triage/repro_705.sh
set -u
cd "$(dirname "$0")/.."   # tools/m11 へ
export FL_WIN64_DIR="${FL_WIN64_DIR:-}"
OUT=work/repro_705; mkdir -p "$OUT"
FAIL=0
run_one() {  # run_one <label> <M11_OV_413060 値>
  local label="$1" gate="$2" t0 t1 rc
  if ! M11_OV_413060="$gate" timeout 300 bash m11_build.sh > "$OUT/build_$label.log" 2>&1; then
    echo "[repro_705] build $label FAILED"; FAIL=1; return 1
  fi
  t0=$(date +%s%N)
  M11_SURVEY_UNITS="$OUT/units_$label.json" timeout 300 node m11_survey.mjs > "$OUT/survey_$label.out" 2>/dev/null; rc=$?
  t1=$(date +%s%N)
  echo "[repro_705] $label: rc=$rc elapsed=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.3f", (b-a)/1e9}') s load=$(cut -d' ' -f1 /proc/loadavg)"
  if [ "$rc" -ne 0 ]; then echo "[repro_705] survey $label FAILED (rc=$rc)"; FAIL=1; fi
  python3 - "$OUT/survey_$label.out" <<'PYS' || FAIL=1
import json, sys
line = next((l for l in open(sys.argv[1]) if l.startswith('M11_SURVEY ')), None)
if line is None:
    print('[repro_705] M11_SURVEY 行が無い'); sys.exit(1)
d = json.loads(line[len('M11_SURVEY '):])
keys = ['ok', 'noproc', 'miss', 'trap', 'clobber', 'f413060_calls']
print('[repro_705] ' + ' '.join(f'{k}={d.get(k)}' for k in keys) + f" f413060_units={len(d.get('f413060_units', []))}")
PYS
}
run_one off 0
run_one on 1
python3 - "$OUT" <<'PYD' || FAIL=1
import json, sys
d = sys.argv[1]
o = json.load(open(f'{d}/units_off.json')); n = json.load(open(f'{d}/units_on.json'))
if len(o) != len(n):
    print(f'[repro_705] unit 数不一致: OFF {len(o)} / ON {len(n)}'); sys.exit(1)
diff = [i for i in range(len(o)) if o[i] != n[i]]
print(f'[repro_705] unit ラベルの OFF/ON 差分: {len(diff)} unit {diff[:20]}')
def summary(p):
    line = next(l for l in open(p) if l.startswith('M11_SURVEY '))
    return json.loads(line[len('M11_SURVEY '):])
so = summary(f'{d}/survey_off.out'); sn = summary(f'{d}/survey_on.out')
keys = ['ok', 'noproc', 'miss', 'trap', 'clobber', 'f413060_calls']
mism = [k for k in keys if so.get(k) != sn.get(k)]
print(f'[repro_705] 計数の OFF/ON 不一致: {mism if mism else "なし"}')
sys.exit(1 if (diff or mism) else 0)
PYD
if [ "$FAIL" -ne 0 ]; then echo "[repro_705] FAIL"; exit 1; fi
echo "[repro_705] PASS"
