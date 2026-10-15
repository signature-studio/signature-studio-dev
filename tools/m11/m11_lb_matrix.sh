#!/usr/bin/env bash
# M11 LB 差の切り分け (#3161): boot5 有無 × ld108 有無 × M11_LB_BASE を 1 通りずつ測る driver.
#   使い方: bash tools/m11/m11_lb_matrix.sh <boot5 0|1> <ld108 0|1> <LB (0 | 0x10000)>
#   前提: work/boot0..4.lift.ll と boot5.lift.ll (boot5 有りのとき) が work/ にある。PE は FL_WIN64_DIR 経由。
#   成果物は work/lbm/<tag>/ に置く (gitignore)。標準出力に 1 行の要約 (LBM_RESULT) を出す。
#   IR 生成 (m11_gen_ir2.sh) → data/image → lb_check → build → 通常起動 (m11_run.mjs) → survey (m11_survey.mjs) の順。
#   boot5 無しは work/boot5.lift.ll を退避 (.off) して gen_ir2 に拾わせない。終了時に元へ戻す。
set -u
cd "$(dirname "$0")"
source ../shared/env.sh
export PE="${M11_PE:-${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}}"
export M11_PE="$PE"
B5="${1:?boot5 0|1}"; LD="${2:?ld108 0|1}"; LB="${3:?LB 0|0x10000}"
export M11_LB_BASE="$LB"
TAG="b5${B5}_ld${LD}_lb$(printf '%s' "$LB" | tr -d 'x')"
D="work/lbm/$TAG"
mkdir -p "$D" work
step() { echo "[lbm $TAG] $*"; }
restore_boot5() { [ -f work/boot5.lift.ll.off ] && mv work/boot5.lift.ll.off work/boot5.lift.ll; }
trap restore_boot5 EXIT
if [ "$B5" = 0 ]; then
  [ -f work/boot5.lift.ll ] && mv work/boot5.lift.ll work/boot5.lift.ll.off
else
  [ -f work/boot5.lift.ll ] || { step "boot5.lift.ll 無し (B5=1 は lift 済みが必要)"; exit 1; }
fi
if [ "$LD" = 0 ]; then export M11_FIX_LD108=0 M11_ALLOW_LD108_DISABLED=1; else unset M11_FIX_LD108 M11_ALLOW_LD108_DISABLED; fi
t_gen=$(date +%s)
bash m11_gen_ir2.sh > "$D/gen.log" 2>&1 || { step "gen_ir2 FAILED ($D/gen.log)"; tail -5 "$D/gen.log"; exit 1; }
t_gen=$(( $(date +%s) - t_gen ))
echo "$LB" > work/ir_lb_base.stamp
echo "$LB" > work/img_lb_base.stamp
rm -f work/m11_data.c work/m11_image.bin
python3 m11_data_gen.py "$PE" > "$D/data.log" 2>&1 || { step "data_gen FAILED"; exit 1; }
python3 m11_image_gen.py "$PE" > "$D/image.log" 2>&1 || { step "image_gen FAILED"; exit 1; }
python3 lb_check.py "$PE" work/m11_image.bin "$LB" > "$D/lb_check.log" 2>&1 || { step "lb_check FAILED"; exit 1; }
t_build=$(date +%s)
bash m11_build.sh > "$D/build.log" 2>&1 || { step "build FAILED ($D/build.log)"; tail -5 "$D/build.log"; exit 1; }
t_build=$(( $(date +%s) - t_build ))
[ -f work/m11_boot.cjs.wasm ] || { step "wasm 未生成"; exit 1; }
cp work/ir_conditions.json "$D/ir_conditions.json"
t_run=$(date +%s)
timeout 300 node m11_run.mjs > "$D/run.out" 2>&1; rc_run=$?
t_run=$(( $(date +%s) - t_run ))
t_survey=$(date +%s)
M11_SURVEY_UNITS="$D/units.json" M11_SURVEY_DETAIL="$D/detail.json" timeout 600 node m11_survey.mjs > "$D/survey.out" 2>&1; rc_survey=$?
t_survey=$(( $(date +%s) - t_survey ))
ir=$(python3 -c "import json;print(json.load(open('work/ir_conditions.json'))['ir_sha256'][:12])")
surv=$(grep '^M11_SURVEY ' "$D/survey.out" | sed 's/^M11_SURVEY //')
echo "$surv" > "$D/survey.json"
echo "LBM_RESULT tag=$TAG boot5=$B5 ld108=$LD LB=$LB ir_sha=$ir rc_run=$rc_run rc_survey=$rc_survey gen_s=$t_gen build_s=$t_build run_s=$t_run survey_s=$t_survey load=$(cut -d' ' -f1 /proc/loadavg)"
python3 - "$D/survey.json" <<'PY'
import json, sys
p = sys.argv[1]
try:
    s = json.loads(open(p).read() or 'null')
except Exception as e:
    print('LBM_SURVEY parse FAILED', e); sys.exit(0)
if s is None:
    print('LBM_SURVEY none'); sys.exit(0)
keys = ['units', 'ok', 'noproc', 'miss', 'trap', 'trap_oom', 'trap_other', 'dllmain_done', 'boot_threw', 'halted_units', 'first_trap_units']
print('LBM_SURVEY ' + ' '.join('%s=%s' % (k, s.get(k)) for k in keys))
PY
grep -E 'units_run|halt0|survey|M11_RESULT|OOB|memory access|threw' "$D/run.out" | head -8 | sed 's/^/LBM_RUN /'
